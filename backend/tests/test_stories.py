"""Story merging: normalisation, the clustering rules and their hard constraints, the
database writes (sources kept, ids stable, idempotent), cached AI verdicts, and the
API changes. The model is always a fake."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from models import Crisis, News, StoryMergeCheck
from services import stories
from services.stories import (
    Ev, cluster_events, is_generated_title, normalize_headline, normalize_url, outlet_of, pick_primary,
    significant_tokens, similarity,
)

NOW = datetime(2026, 10, 4, 12, 0, 0)


def ev(id, title='Two soldiers killed in border clash near Rafah', url=None, country='Israel', scope='global',
       kind='physical', lat=31.3, lon=34.2, hours=0, confidence=55):
    return Ev(id, title, url if url is not None else f'https://site-{id}.example/{id}', country, scope, kind, lat, lon,
              NOW - timedelta(hours=hours), confidence)


def groups(events, judge=None):
    clusters, stats = cluster_events(events, judge=judge)
    return sorted(sorted(e.id for e in c) for c in clusters), stats


# --- normalisation ------------------------------------------------------------------------

class TestNormalise:
    @pytest.mark.parametrize('a,b', [
        ('https://www.Example.com/a/b/', 'http://example.com/a/b'),
        ('https://example.com/a?utm_source=x&utm_medium=y', 'https://example.com/a'),
        ('https://example.com/a#section', 'https://example.com/a'),
        ('https://example.com/a?fbclid=1&id=5', 'https://example.com/a?id=5'),
        ('https://example.com/a?b=2&a=1', 'https://example.com/a?a=1&b=2'),
    ])
    def test_the_same_article_under_different_spellings(self, a, b):
        assert normalize_url(a) == normalize_url(b)

    def test_different_query_ids_are_different_articles(self):
        assert normalize_url('https://example.com/read?id=1') != normalize_url('https://example.com/read?id=2')

    @pytest.mark.parametrize('bad', [None, '', '   ', 5, 'not a url', '///'])
    def test_unusable_urls(self, bad):
        assert normalize_url(bad) is None

    def test_outlet_is_the_host_without_www(self):
        assert outlet_of('https://www.Reuters.com/world/x') == 'reuters.com'
        assert outlet_of('https://news.bbc.co.uk/a') == 'news.bbc.co.uk'
        assert outlet_of(None) is None and outlet_of('nonsense') is None

    def test_headlines_ignore_case_punctuation_and_accents(self):
        assert normalize_headline('  Café ATTACK: 5 dead!! ') == 'cafe attack 5 dead'
        assert normalize_headline(None) == '' and normalize_headline('') == ''

    def test_filler_and_decoration_words_carry_no_identity(self):
        assert significant_tokens('BREAKING: Five miners killed in Plateau attack') == frozenset(
            {'five', 'miners', 'killed', 'plateau', 'attack'})

    def test_similarity_is_jaccard(self):
        a, b = significant_tokens('miners killed plateau attack'), significant_tokens('miners killed plateau raid')
        assert similarity(a, b) == pytest.approx(3 / 5)
        assert similarity(a, a) == 1.0
        assert similarity(a, frozenset()) == 0.0 and similarity(frozenset(), frozenset()) == 0.0


# --- tier 1 ----------------------------------------------------------------------------------

class TestClearCases:
    def test_same_article_is_one_story(self):
        assert groups([ev('a', url='https://x.com/1', title='One thing happened'),
                       ev('b', url='https://www.x.com/1/', title='Entirely different words here')])[0] == [['a', 'b']]

    def test_same_headline_from_different_outlets_is_one_story(self):
        assert groups([ev('a'), ev('b')])[0] == [['a', 'b']]

    def test_a_very_short_headline_is_not_identity(self):
        assert groups([ev('a', title='Gaza'), ev('b', title='Gaza')])[0] == [['a'], ['b']]

    def test_very_similar_wording_at_the_same_place_and_day_is_one_story(self):
        a = ev('a', title='Five miners killed in Plateau attack, others injured')
        b = ev('b', title='5 miners killed in Plateau attack, others injured', hours=3)
        c = ev('c', title='Five miners killed in Plateau state attack, others injured', hours=5)
        assert groups([a, b, c])[0] == [['a', 'b', 'c']]

    def test_different_stories_stay_apart(self):
        assert groups([ev('a', title='Soldiers killed in border clash near Rafah'),
                       ev('b', title='Parliament passes new budget after long debate')])[0] == [['a'], ['b']]

    @pytest.mark.parametrize('field,value', [('country', 'Egypt'), ('scope', 'local'), ('kind', 'statement')])
    def test_similar_but_not_identical_wording_never_merges_across_country_scope_or_kind(self, field, value):
        a = ev('a', title='Five miners killed in Plateau attack, others injured')
        b = ev('b', title='5 miners killed in Plateau attack, others injured', **{field: value})
        assert groups([a, b])[0] == [['a'], ['b']]

    def test_one_article_tagged_with_several_countries_is_one_story(self):
        url = 'https://example.com/the-same-article'
        events = [ev('a', url=url, country='Iraq'), ev('b', url=url, country='Syria'), ev('c', url=url, country='Turkey')]
        assert groups(events)[0] == [['a', 'b', 'c']]
        title = 'American ignorance risks fueling deadly Middle East sectarianism'
        assert groups([ev('a', title=title, country='Iraq'), ev('b', title=title, country='Lebanon', hours=3)])[0] == [['a', 'b']]

    def test_the_country_the_headline_names_becomes_the_pin(self):
        title = 'Houthis claim new attack on airport in Saudi Arabia as witnesses report evacuation'
        a = ev('a', title=title, country='Egypt', hours=5)
        b = ev('b', title=title, country='Saudi Arabia', hours=1)
        assert pick_primary([a, b]).id == 'b'

    def test_never_merges_events_more_than_two_days_apart(self):
        assert groups([ev('a'), ev('b', hours=49)])[0] == [['a'], ['b']]
        assert groups([ev('a'), ev('b', hours=47)])[0] == [['a', 'b']]

    def test_similar_wording_needs_the_same_day_but_an_identical_headline_does_not(self):
        similar = dict(title='Five miners killed in Plateau attack, others injured')
        assert groups([ev('a', **similar), ev('b', hours=30, **similar)])[0] == [['a', 'b']]   # identical headline
        a = ev('a', title='Five miners killed in Plateau attack, others injured')
        b = ev('b', title='5 miners killed in Plateau attack, others injured', hours=30)
        assert groups([a, b])[0] == [['a'], ['b']]                                           # only similar

    def test_similar_wording_far_apart_is_not_one_story(self):
        a = ev('a', title='Five miners killed in Plateau attack, others injured', lat=9.9, lon=8.9)
        b = ev('b', title='5 miners killed in Plateau attack, others injured', lat=6.5, lon=3.4)
        assert groups([a, b])[0] == [['a'], ['b']]

    def test_merging_is_transitive(self):
        assert groups([ev('a', url='https://x.com/1'), ev('b', url='https://x.com/1', title='Other words entirely'),
                       ev('c', title='Other words entirely')])[0] == [['a', 'b', 'c']]

    def test_events_without_a_country_are_left_alone(self):
        a = ev('a', country=None, title='Five miners killed in Plateau attack, others injured')
        b = ev('b', country=None, title='5 miners killed in Plateau attack, others injured')
        assert groups([a, b])[0] == [['a'], ['b']]   # similar wording needs a known country; an identical headline or URL does not

    def test_primary_is_the_earliest_then_the_most_confident_then_the_id(self):
        assert pick_primary([ev('b', hours=1), ev('a', hours=5), ev('c', hours=2)]).id == 'a'
        assert pick_primary([ev('x', hours=1, confidence=60), ev('y', hours=1, confidence=90)]).id == 'y'
        assert pick_primary([ev('m', hours=1), ev('k', hours=1)]).id == 'k'


# --- the feed's stand-in titles are not headlines ---------------------------------------------

class TestStandInTitles:
    @pytest.mark.parametrize('title', [
        'Conflict-related event in United States', 'Police fights United States', 'Deputy criticizes Iran',
        'Israel criticizes Saudi Arabia', 'Society Of Friends demands action from United States',
        'Gunmen — conflict-related event in Nigeria', 'Army shows military force near Taiwan', '', '   ', None,
    ])
    def test_stand_ins(self, title):
        assert is_generated_title(title) is True

    @pytest.mark.parametrize('title', [
        'Boise man gets suspended sentence for assault, resisting arrest', 'Five miners killed in Plateau attack',
        'Trump rejects Iran’s seven-day roadmap', 'Iran seizes tanker in Hormuz',
        'Karnataka high court awards Rs 2.8 crore to Bengaluru man',
    ])
    def test_real_headlines(self, title):
        assert is_generated_title(title) is False

    def test_identical_stand_ins_are_not_one_story(self):
        a, b = ev('a', title='Police fights United States'), ev('b', title='Police fights United States')
        assert groups([a, b])[0] == [['a'], ['b']]

    def test_stand_ins_do_not_match_on_similar_wording_either(self):
        a, b = ev('a', title='Police fights United States'), ev('b', title='Deputy fights United States')
        assert groups([a, b])[0] == [['a'], ['b']]

    def test_stand_ins_citing_the_same_article_are_one_story(self):
        a = ev('a', title='Police fights United States', url='https://x.com/one')
        b = ev('b', title='Deputy fights United States', url='https://www.x.com/one/')
        assert groups([a, b])[0] == [['a', 'b']]

    def test_a_stand_in_never_pulls_in_a_real_headline_by_wording(self):
        a = ev('a', title='Five miners killed in Plateau attack, others injured')
        b = ev('b', title='Miners fights Plateau')
        assert groups([a, b])[0] == [['a'], ['b']]


# --- tier 2 -----------------------------------------------------------------------------------

BORDER_A = 'Five miners killed in Plateau attack, police say'
BORDER_B = 'Gunmen kill five miners in Plateau attack'


class TestBorderline:
    def pair(self, **kwargs):
        return [ev('a', title=BORDER_A, **kwargs), ev('b', title=BORDER_B, hours=2, **kwargs)]

    def test_the_wording_really_is_borderline(self):
        score = similarity(significant_tokens(BORDER_A), significant_tokens(BORDER_B))
        assert stories.SIMILARITY_BORDERLINE <= score < stories.SIMILARITY_AUTO

    def test_without_a_judge_a_borderline_pair_stays_apart(self):
        assert groups(self.pair())[0] == [['a'], ['b']]

    @pytest.mark.parametrize('verdict,expected', [(True, [['a', 'b']]), (False, [['a'], ['b']]), (None, [['a'], ['b']])])
    def test_the_judges_verdict_decides(self, verdict, expected):
        result, stats = groups(self.pair(), judge=lambda a, b: verdict)
        assert result == expected
        assert stats['tier2_merged'] == (1 if verdict else 0)

    def test_statements_are_never_sent_to_the_judge(self):
        asked = []
        groups(self.pair(kind='statement'), judge=lambda a, b: asked.append(1) or True)
        assert asked == []

    def test_a_pair_of_stories_is_only_asked_about_once(self):
        a1, a2 = ev('a1', title=BORDER_A), ev('a2', title=BORDER_A, hours=1)
        b1, b2 = ev('b1', title=BORDER_B, hours=2), ev('b2', title=BORDER_B, hours=3)
        asked = []
        result, _ = groups([a1, a2, b1, b2], judge=lambda a, b: asked.append((a.id, b.id)) or True)
        assert result == [['a1', 'a2', 'b1', 'b2']] and len(asked) == 1


# --- the database --------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean(app_module, client, db_session):
    client.get('/api/health')
    for model in (News, StoryMergeCheck, Crisis):
        db_session.query(model).delete()
    db_session.commit()
    yield
    for model in (News, StoryMergeCheck, Crisis):
        db_session.query(model).delete()
    db_session.commit()


def seed(db, id, title='Two soldiers killed in border clash near Rafah', url=None, country='Israel', kind='physical',
         lat=31.3, lon=34.2, hours=1, confidence=55, source='GDELT', scope='global', active=True):
    db.add(Crisis(id=id, type='conflict', title=title, country=country, latitude=lat, longitude=lon, severity=60,
                  source=source, source_url=url if url is not None else f'https://{id}.example/story', scope=scope,
                  event_kind=kind, is_active=active, confidence=confidence,
                  date_start=datetime.utcnow() - timedelta(hours=hours)))
    db.commit()


def row(db, id):
    db.expire_all()
    return db.query(Crisis).filter(Crisis.id == id).first()


def news_for(db, id):
    db.expire_all()
    return db.query(News).filter(News.crisis_id == id).order_by(News.url).all()


class TestMergeRecent:
    def test_repeats_become_one_story_that_names_every_source(self, db_session):
        seed(db_session, 'g1', url='https://reuters.com/a', hours=5)
        seed(db_session, 'g2', url='https://apnews.com/b', hours=3)
        seed(db_session, 'g3', url='https://bbc.co.uk/c', hours=1)
        summary = stories.merge_recent(ai_per_run=0)
        assert summary['stories_merged'] == 1 and summary['events_merged'] == 2
        primary = row(db_session, 'g1')
        assert primary.is_active and primary.merged_into is None and primary.source_count == 3
        for dupe in ('g2', 'g3'):
            assert row(db_session, dupe).is_active is False and row(db_session, dupe).merged_into == 'g1'
        sources = news_for(db_session, 'g1')
        assert sorted(n.source for n in sources) == ['apnews.com', 'bbc.co.uk', 'reuters.com']
        assert sorted(n.url for n in sources) == ['https://apnews.com/b', 'https://bbc.co.uk/c', 'https://reuters.com/a']
        assert all(n.title and n.published_at for n in sources)

    def test_confidence_rises_with_the_number_of_outlets(self, db_session):
        seed(db_session, 'g1', hours=5, confidence=55)
        seed(db_session, 'g2', hours=4)
        seed(db_session, 'g3', hours=3)
        stories.merge_recent(ai_per_run=0)
        assert row(db_session, 'g1').confidence == 65          # 50 + 5 * 3 outlets

    def test_two_articles_from_one_outlet_count_as_one_source(self, db_session):
        seed(db_session, 'g1', url='https://reuters.com/a', hours=5)
        seed(db_session, 'g2', url='https://www.reuters.com/b', hours=4)
        stories.merge_recent(ai_per_run=0)
        assert row(db_session, 'g1').source_count == 1 and len(news_for(db_session, 'g1')) == 2

    def test_the_same_article_twice_is_stored_once(self, db_session):
        seed(db_session, 'g1', url='https://x.com/a', hours=5)
        seed(db_session, 'g2', url='https://www.x.com/a/', hours=4)
        stories.merge_recent(ai_per_run=0)
        assert len(news_for(db_session, 'g1')) == 1

    def test_the_primary_keeps_its_id_and_nothing_is_deleted(self, db_session):
        seed(db_session, 'g1', hours=5)
        seed(db_session, 'g2', hours=1)
        stories.merge_recent(ai_per_run=0)
        assert db_session.query(Crisis).count() == 2

    def test_running_again_changes_nothing(self, db_session):
        seed(db_session, 'g1', hours=5)
        seed(db_session, 'g2', hours=1)
        stories.merge_recent(ai_per_run=0)
        before = [(n.id, n.url) for n in news_for(db_session, 'g1')]
        again = stories.merge_recent(ai_per_run=0)
        assert again['stories_merged'] == 0
        assert [(n.id, n.url) for n in news_for(db_session, 'g1')] == before
        assert row(db_session, 'g1').source_count == 2

    def test_a_late_article_joins_the_existing_story(self, db_session):
        seed(db_session, 'g1', url='https://a.example/1', hours=20)
        seed(db_session, 'g2', url='https://b.example/2', hours=19)
        stories.merge_recent(ai_per_run=0)
        seed(db_session, 'g3', url='https://c.example/3', hours=1)
        summary = stories.merge_recent(ai_per_run=0)
        assert summary['events_merged'] == 1
        assert row(db_session, 'g3').merged_into == 'g1'
        assert row(db_session, 'g1').source_count == 3 and len(news_for(db_session, 'g1')) == 3

    def test_two_existing_stories_that_turn_out_to_be_one_are_joined_with_all_sources(self, db_session):
        seed(db_session, 'p1', title='Five miners killed in Plateau attack, others injured', url='https://a.example/1', hours=30)
        seed(db_session, 'p1b', title='Five miners killed in Plateau attack, others injured', url='https://b.example/1', hours=29)
        seed(db_session, 'p2', title='Gunmen raid Jos village, dozens dead', url='https://c.example/2', hours=10, country='Israel')
        seed(db_session, 'p2b', title='Gunmen raid Jos village, dozens dead', url='https://d.example/2', hours=9)
        stories.merge_recent(ai_per_run=0)
        assert row(db_session, 'p2').source_count == 2
        # a bridging article ties the two stories together (same article as p2's, same headline as p1's)
        seed(db_session, 'bridge1', title='Five miners killed in Plateau attack, others injured', url='https://c.example/2', hours=8)
        stories.merge_recent(ai_per_run=0)
        assert row(db_session, 'p2').merged_into == 'p1' and row(db_session, 'p2').is_active is False
        assert row(db_session, 'p1').source_count == 4
        assert sorted(n.source for n in news_for(db_session, 'p1')) == ['a.example', 'b.example', 'c.example', 'd.example']
        assert news_for(db_session, 'p2') == []

    def test_only_active_gdelt_events_inside_the_window_are_considered(self, db_session):
        seed(db_session, 'g1', hours=5)
        seed(db_session, 'old', hours=24 * 5)                       # outside a 3 day window
        seed(db_session, 'archived', hours=4, active=False)         # not active
        seed(db_session, 'news', hours=3, source='NewsAPI')         # not GDELT
        summary = stories.merge_recent(days=3, ai_per_run=0)
        assert summary['events'] == 1 and summary['stories_merged'] == 0

    def test_a_wider_window_reaches_older_events(self, db_session):
        seed(db_session, 'a', hours=24 * 5)
        seed(db_session, 'b', hours=24 * 5 - 1)
        assert stories.merge_recent(days=3, ai_per_run=0)['stories_merged'] == 0
        assert stories.merge_recent(days=7, ai_per_run=0)['stories_merged'] == 1

    def test_the_events_cache_is_cleared_only_when_something_merged(self, db_session):
        seed(db_session, 'g1')
        with patch.object(stories, 'cache_clear_prefix') as clear:
            stories.merge_recent(ai_per_run=0)
            clear.assert_not_called()
            seed(db_session, 'g2')
            stories.merge_recent(ai_per_run=0)
            clear.assert_called_once_with('crises:')

    def test_a_failure_leaves_the_database_untouched(self, db_session):
        seed(db_session, 'g1', hours=5)
        seed(db_session, 'g2', hours=1)
        with patch.object(stories, '_merge_cluster', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                stories.merge_recent(ai_per_run=0)
        assert row(db_session, 'g2').is_active is True and row(db_session, 'g2').merged_into is None


class TestModelVerdicts:
    A = 'Five miners killed in Plateau attack, police say'
    B = 'Gunmen kill five miners in Plateau attack'

    def setup_pair(self, db):
        seed(db, 'g1', title=self.A, hours=3)
        seed(db, 'g2', title=self.B, hours=1)

    def test_a_yes_merges_and_is_remembered(self, db_session):
        self.setup_pair(db_session)
        with patch.object(stories, '_model_available', return_value=True), \
                patch.object(stories, '_ask_model', return_value=True) as ask:
            summary = stories.merge_recent(ai_per_run=5)
        assert ask.call_count == 1 and summary['tier2_merged'] == 1
        assert row(db_session, 'g2').merged_into == 'g1'
        assert db_session.query(StoryMergeCheck).filter(StoryMergeCheck.pair_key == 'g1|g2').first().same_event is True

    def test_a_no_is_remembered_and_never_asked_again(self, db_session):
        self.setup_pair(db_session)
        with patch.object(stories, '_model_available', return_value=True), \
                patch.object(stories, '_ask_model', return_value=False) as ask:
            stories.merge_recent(ai_per_run=5)
            stories.merge_recent(ai_per_run=5)
        assert ask.call_count == 1
        assert row(db_session, 'g2').merged_into is None

    def test_the_per_run_budget_is_respected(self, db_session):
        for i in range(4):
            seed(db_session, f'a{i}', title=f'{self.A} {i}', hours=3, lat=31.3 + i)
            seed(db_session, f'b{i}', title=f'{self.B} {i}', hours=1, lat=31.3 + i)
        with patch.object(stories, '_model_available', return_value=True), \
                patch.object(stories, '_ask_model', return_value=False) as ask:
            stories.merge_recent(ai_per_run=2)
        assert ask.call_count == 2

    def test_no_model_means_borderline_pairs_stay_apart(self, db_session):
        self.setup_pair(db_session)
        with patch.object(stories, '_model_available', return_value=False), \
                patch.object(stories, '_ask_model') as ask:
            summary = stories.merge_recent(ai_per_run=5)
        ask.assert_not_called()
        assert summary['tier2_merged'] == 0 and row(db_session, 'g2').merged_into is None

    def test_a_model_failure_is_not_remembered(self, db_session):
        self.setup_pair(db_session)
        with patch.object(stories, '_model_available', return_value=True), \
                patch.object(stories, '_ask_model', side_effect=RuntimeError('overloaded')):
            stories.merge_recent(ai_per_run=5)
        assert db_session.query(StoryMergeCheck).count() == 0
        assert row(db_session, 'g2').merged_into is None

    def test_an_unclear_answer_is_not_remembered(self, db_session):
        self.setup_pair(db_session)
        with patch.object(stories, '_model_available', return_value=True), \
                patch.object(stories, '_ask_model', return_value=None):
            stories.merge_recent(ai_per_run=5)
        assert db_session.query(StoryMergeCheck).count() == 0

    def test_budget_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv('STORY_MERGE_AI_PER_RUN', '7')
        assert stories.ai_budget() == 7
        monkeypatch.setenv('STORY_MERGE_AI_PER_RUN', 'many')
        assert stories.ai_budget() == stories.DEFAULT_AI_PER_RUN
        monkeypatch.setenv('STORY_MERGE_AI_PER_RUN', '-3')
        assert stories.ai_budget() == 0


# --- ids and the API -------------------------------------------------------------------------------

def test_canonical_id_follows_a_merge(db_session):
    seed(db_session, 'g1', hours=5)
    seed(db_session, 'g2', hours=1)
    stories.merge_recent(ai_per_run=0)
    assert stories.canonical_id('g2') == 'g1' and stories.canonical_id('g1') == 'g1'
    assert stories.canonical_id('does-not-exist') == 'does-not-exist'


class TestApi:
    def test_the_list_shows_stories_not_their_duplicates_and_counts_sources(self, client, db_session):
        seed(db_session, 'g1', hours=5)
        seed(db_session, 'g2', hours=4)
        seed(db_session, 'solo', title='Parliament passes new budget after long debate', country='France', hours=3)
        stories.merge_recent(ai_per_run=0)
        rows = {r['id']: r for r in client.get('/api/crises?view=map').get_json()['crises']}
        assert set(rows) == {'g1', 'solo'}
        assert rows['g1']['sources'] == 2 and 'sources' not in rows['solo']

    def test_a_merged_event_opens_as_its_story_with_every_source(self, client, db_session):
        seed(db_session, 'g1', url='https://a.example/1', hours=5)
        seed(db_session, 'g2', url='https://b.example/2', hours=4)
        stories.merge_recent(ai_per_run=0)
        body = client.get('/api/crises/g2').get_json()
        assert body['id'] == 'g1' and body['merged_from'] == 'g2' and body['source_count'] == 2
        assert sorted(n['source'] for n in body['news']) == ['a.example', 'b.example']
        direct = client.get('/api/crises/g1').get_json()
        assert direct['id'] == 'g1' and 'merged_from' not in direct

    def test_briefing_and_scenarios_resolve_a_merged_id(self, client, db_session, monkeypatch):
        seed(db_session, 'g1', hours=5)
        seed(db_session, 'g2', hours=4)
        stories.merge_recent(ai_per_run=0)
        with patch('blueprints.crises.generate_ai_briefing', return_value={'ok': True}) as briefing:
            client.get('/api/crises/g2/briefing')
        briefing.assert_called_once_with('g1')

    def test_to_dict_exposes_the_story_fields(self, db_session):
        seed(db_session, 'g1')
        body = row(db_session, 'g1').to_dict()
        assert body['source_count'] == 1 and body['merged_into'] is None


class TestJunkAndTags:
    @pytest.mark.parametrize('title,why', [
        ('Facebook', 'site'), ('newsroomamerica.com — newsroomamerica.com', 'domain'), ('example.co.uk', 'domain'),
        ('Conflict-related event in India', 'template'), ('', 'domain'),
    ])
    def test_junk_titles(self, title, why):
        from services.stories import junk_reason
        assert junk_reason(title) == why

    @pytest.mark.parametrize('title', ['Facebook fined 5 million over data leak', 'Student fights Uganda', 'Rubio wants Europe awake'])
    def test_real_headlines_are_not_junk(self, title):
        from services.stories import junk_reason
        assert junk_reason(title) is None


class TestCrossCountryAndHidden:
    def test_one_article_tagged_with_countries_becomes_one_pin_and_remembers_the_others(self, db_session):
        url = 'https://example.com/one-article'
        title = 'American ignorance risks fueling deadly Middle East sectarianism'
        seed(db_session, 'i1', title=title, url=url, country='Iraq', hours=5)
        seed(db_session, 'i2', title=title, url=url, country='Lebanon', hours=4)
        seed(db_session, 'i3', title=title, url=url, country='Syria', hours=3)
        stories.merge_recent(ai_per_run=0)
        live = [i for i in ('i1', 'i2', 'i3') if row(db_session, i).is_active]
        assert live == ['i1']
        assert sorted(row(db_session, 'i1').to_dict()['also_tagged']) == ['Lebanon', 'Syria']

    def test_junk_titles_are_hidden_with_a_reason_and_nothing_is_deleted(self, db_session):
        seed(db_session, 'j1', title='Facebook', hours=2)
        seed(db_session, 'j2', title='Conflict-related event in India', hours=2, country='India')
        seed(db_session, 'ok', title='Two soldiers killed in border clash near Rafah', hours=2)
        summary = stories.merge_recent(ai_per_run=0)
        assert summary['hidden'] == 2
        assert (row(db_session, 'j1').is_active, row(db_session, 'j1').hidden_reason) == (False, 'site')
        assert row(db_session, 'j2').hidden_reason == 'template'
        assert row(db_session, 'ok').is_active and row(db_session, 'ok').hidden_reason is None
        assert db_session.query(Crisis).count() == 3
