"""The keyless situation view (services/situation_view.py)."""
from datetime import datetime, timedelta
from unittest.mock import patch

from models import Crisis, Situation
from services.situation_view import key_sentences, pick_angles, stated_figures


def test_figures_are_only_what_the_text_states_and_are_not_summed():
    texts = ['Houthi attacks on Saudi airports kill 3, injure 36', 'Three killed and dozens injured in attacks',
             'At least three people were killed, 36 wounded', 'Fighting continues in Taiz']
    got = {(f['count'], f['kind']): f['stated_in'] for f in stated_figures(texts)}
    assert got[(3, 'killed')] == [0, 1, 2]
    assert got[(36, 'injured')] == [0, 2]
    assert (39, 'killed') not in got


def test_no_figure_without_a_number_that_attaches_to_killed_or_injured():
    assert stated_figures(['2026 budget passes with 5 amendments', 'Dozens injured in blast']) == []


def test_angles_pick_headlines_that_differ_and_skip_rewordings():
    heads = ['Maduro and wife charged with torture', 'Maduro, wife face torture charges',
             'FBI director addresses new indictment of Maduro', 'Venezuela reacts to US indictment of ousted leader']
    chosen = pick_angles(heads, 3)
    assert chosen[0] == 0 and 1 not in chosen[:2]


def test_key_sentences_are_those_other_stories_echo():
    echoed = 'Three people were killed and 36 injured when missiles struck airports in Riyadh and Abha on Tuesday.'
    stories = [
        {'text': echoed + ' The weather in Riyadh was clear that evening with light winds.', 'title': 'Houthi missiles hit Saudi airports', 'outlet': 'a.com', 'url': 'https://a.com/1'},
        {'text': 'Officials said three people were killed and 36 injured as missiles struck the airports in Riyadh and Abha.', 'title': 'Saudi airports struck by Houthi missiles', 'outlet': 'b.com', 'url': 'https://b.com/2'},
        {'text': 'Unrelated line about the shipping calendar for the season ahead in the region.', 'title': 'Houthi attack airports Saudi Arabia', 'outlet': 'c.com', 'url': 'https://c.com/3'},
    ]
    out = key_sentences(stories, limit=2)
    assert out and 'killed' in out[0]['text'] and out[0]['echoed_by'] >= 1
    assert all(len(s['text']) <= 260 for s in out)
    assert not any('weather' in s['text'] for s in out[:1])


def test_endpoint_returns_the_view_and_null_for_a_lone_story(app_module, client, db_session):
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()
    now = datetime.utcnow()
    heads = ['Houthi missiles hit Saudi airports, three killed', 'Three killed as Houthis strike Saudi airports', 'Saudi airports attacked by Houthis, 36 injured']
    for i, t in enumerate(heads):
        db_session.add(Crisis(id=f'v{i}', type='conflict', title=t, country='Saudi Arabia', latitude=25, longitude=45, severity=60, is_active=True,
                              source='GDELT', source_url=f'https://o{i}.example/a', date_start=now - timedelta(hours=5 - i), source_count=1, situation_id='v0'))
    db_session.add(Crisis(id='solo', type='conflict', title='Something else', country='Peru', latitude=0, longitude=0, severity=40, is_active=True,
                          date_start=now))
    db_session.add(Situation(id='v0', title=heads[0], country='Saudi Arabia', story_count=3, source_total=3, first_at=now, last_at=now))
    db_session.commit()
    with patch('services.situation_view.fetch_real_page_metadata', return_value={'description': None, 'excerpt': 'Three people were killed and 36 injured when missiles struck airports in Riyadh and Abha on Tuesday.'}):
        data = client.get('/api/crises/v1/situation').get_json()['situation']
    assert data['story_count'] == 3 and data['id'] == 'v0' and len(data['stories']) == 3
    assert any(f['count'] == 3 and f['kind'] == 'killed' for f in data['figures'])
    assert client.get('/api/crises/solo/situation').get_json() == {'situation': None}
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()


def test_the_map_list_shows_one_pin_per_situation_with_its_story_count(app_module, client, db_session):
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()
    now = datetime.utcnow()
    for i in range(3):
        db_session.add(Crisis(id=f'p{i}', type='conflict', title=f'Houthi strike on Saudi airport variant {i}', country='Saudi Arabia', latitude=25, longitude=45,
                              severity=60, is_active=True, source='GDELT', source_url=f'https://o{i}.example/a', date_start=now - timedelta(hours=5 - i),
                              situation_id='p0', source_count=1))
    db_session.add(Crisis(id='alone', type='conflict', title='Unrelated event', country='Peru', latitude=0, longitude=0, severity=40, is_active=True, date_start=now))
    db_session.add(Situation(id='p0', title='x', country='Saudi Arabia', story_count=3, source_total=3, first_at=now, last_at=now))
    db_session.commit()
    data = client.get('/api/crises?view=map&scope=global&days=2').get_json()
    rows = data['crises'] if isinstance(data, dict) else data
    ids = {c['id']: c for c in rows}
    assert 'p1' not in ids and 'p2' not in ids and 'alone' in ids
    assert ids['p0']['stories'] == 3 and ids['p0']['sources'] == 3
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()
