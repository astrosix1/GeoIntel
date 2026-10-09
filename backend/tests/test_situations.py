"""Grouping related stories into situations (services/situations.py)."""
from datetime import datetime, timedelta

import pytest

from models import Crisis, Situation
from services import situations
from services.situations import Item, group_items, headline_of

NOW = datetime(2026, 10, 8, 12, 0)


def item(id, title, country='United States', hours=0, lat=38.0, lon=-77.0, tagged=()):
    return Item(id, title, country, tagged, lat, lon, NOW - timedelta(hours=hours))


def ids(groups):
    return sorted(sorted(i.id for i in g) for g in groups)


MADURO = [
    'Former Venezuelan President Nicolas Maduro, Wife Charged With Torture',
    "Venezuela's Nicolas Maduro and his wife charged over torture allegations - Grenada Chronicle",
    'US Prosecutors Charge Ex-Venezuelan Leader Nicolas Maduro, Wife With Torture Conspiracy',
    'Nicolas Maduro and wife charged with torturing US citizens in new indictment',
]
FILLER = [  # unrelated headlines so word rarity means something
    f'{a} {b} {c} reported on Tuesday' for a, b, c in
    [('Storm', 'hits', 'Florida coast'), ('Budget', 'vote', 'delayed in Ottawa'), ('Striker', 'signs', 'record Madrid deal'),
     ('Volcano', 'erupts', 'near Catania'), ('Court', 'blocks', 'Texas law'), ('Fire', 'closes', 'Sydney tunnel')]]


def test_headlines_about_one_event_become_one_situation():
    items = [item(f'm{i}', t, hours=i) for i, t in enumerate(MADURO)] + [item(f'f{i}', t, lat=10 + 5 * i, lon=20 + 9 * i) for i, t in enumerate(FILLER)]
    groups = group_items(items)
    assert ['m0', 'm1', 'm2', 'm3'] in ids(groups)
    assert len([g for g in groups if len(g) > 1]) == 1


def test_unrelated_headlines_stay_apart():
    items = [item(f'f{i}', t, lat=10 + 5 * i, lon=20 + 9 * i) for i, t in enumerate(FILLER)]
    assert all(len(g) == 1 for g in group_items(items))


def test_stories_days_apart_are_not_one_situation():
    a, b = item('a', MADURO[0]), item('b', MADURO[2], hours=24 * 5)
    assert all(len(g) == 1 for g in group_items([a, b] + [item(f'f{i}', t, lat=10 + 5 * i) for i, t in enumerate(FILLER)]))


def test_headlines_naming_different_countries_do_not_link():
    a = item('a', 'Peru Politics Explained, Who Holds Power in 2026', country='Peru', lat=-9, lon=-75)
    b = item('b', 'Mexico Politics Explained, Who Holds Power in 2026', country='Mexico', lat=19, lon=-99)
    assert all(len(g) == 1 for g in group_items([a, b] + [item(f'f{i}', t, lat=10 + 5 * i) for i, t in enumerate(FILLER)]))


def test_a_recurring_dated_feature_is_not_one_event():
    a = item('a', 'Arrests In Brevard County: October 5, 2026 - Suspects Presumed Innocent Until Proven Guilty')
    b = item('b', 'Arrests In Brevard County: October 6, 2026 - Suspects Presumed Innocent Until Proven Guilty', hours=3)
    assert all(len(g) == 1 for g in group_items([a, b] + [item(f'f{i}', t, lat=10 + 5 * i) for i, t in enumerate(FILLER)]))


def test_size_is_capped():
    same = [item(f'm{i}', f'Houthi missile strike hits Saudi airport variant{i % 3} report', country='Saudi Arabia', hours=i % 20, lat=25, lon=45) for i in range(40)]
    assert max(len(g) for g in group_items(same + [item(f'f{i}', t, lat=10 + 5 * i) for i, t in enumerate(FILLER)])) <= situations.MAX_SIZE


def test_mojibake_and_wire_tails_are_cleaned():
    assert headline_of('Former president NicolÃ¡s Maduro charged') == 'Former president Nicolás Maduro charged'
    assert headline_of('Saudi-led coalition, Houthis trade strikes, casualties reported-Xinhua') == 'Saudi-led coalition, Houthis trade strikes, casualties reported'
    assert headline_of('Hamas-Israel') == 'Hamas-Israel'


def test_outlet_decoration_is_stripped():
    assert headline_of('Police admit error | National News | site.com') == 'Police admit error'
    assert headline_of("Andrew's warrants unlawful - AL-MONITOR: The Middle East's leading source") == "Andrew's warrants unlawful"


@pytest.fixture
def clean(app_module, client, db_session):
    client.get('/api/health')
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()
    yield
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()


def test_build_recent_stores_situations_and_is_repeatable(clean, db_session):
    for i, t in enumerate(MADURO):
        db_session.add(Crisis(id=f'm{i}', type='conflict', title=t, country='Venezuela', latitude=10, longitude=-66, severity=50, is_active=True,
                              source='GDELT', source_url=f'https://s{i}.example/a', date_start=datetime.utcnow() - timedelta(hours=10 - i), source_count=2))
    for i, t in enumerate(FILLER):
        db_session.add(Crisis(id=f'f{i}', type='conflict', title=t, country='Canada', latitude=40 + 5 * i, longitude=-100 + 9 * i, severity=50,
                              is_active=True, source='GDELT', source_url=f'https://f{i}.example/a', date_start=datetime.utcnow() - timedelta(hours=3)))
    db_session.commit()
    first = situations.build_recent()
    assert first['situations'] == 1 and first['stories_grouped'] == 4
    db_session.expire_all()
    s = db_session.get(Situation, 'm0')
    assert (s.story_count, s.source_total) == (4, 8)
    assert {c.situation_id for c in db_session.query(Crisis).filter(Crisis.id.like('m%'))} == {'m0'}
    assert db_session.query(Crisis).filter(Crisis.id.like('f%'), Crisis.situation_id.isnot(None)).count() == 0
    assert situations.build_recent()['situations'] == 1 and db_session.query(Situation).count() == 1
