"""
Tests for event_pipeline/relevance.py — outlet filtering and the per-source
geopolitical relevance rules (GDELT strict rules, NewsAPI actor/topic rules,
ACLED sub-type rules). Fixtures are modelled on real items that reached the
globe before these rules existed: an F1 article pinned as a conflict in
Baku, a 1934 cruise-ship history piece coded as a FIGHT, US local crime
coded as state violence, and celebrity/sport stories.
"""
import pytest

import data_sources as ds
import event_pipeline
from event_pipeline.relevance import check_outlet, check_gdelt, check_news, check_acled, is_off_topic


# ── outlets ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('url,outlet,expected', [
    ('https://www.crash.net/f1/news/1105752/lando-norris-wants-ban', None, 'blocked_outlet'),
    ('https://www.prnewswire.com/news-releases/acme-launches-x.html', None, 'blocked_outlet'),
    ('https://edition.espn.com/soccer/story/x', None, 'blocked_outlet'),       # subdomain
    ('https://example.com/a', 'Biztoc.com', 'blocked_outlet'),
    ('https://www.theguardian.com/sport/2026/sep/25/match-report', None, 'blocked_section'),
    ('https://www.philstar.com/opinion/2026/09/27/2559138/editorial-lessons', None, 'blocked_section'),
    ('https://news.site/entertainment-news/celebrity-x', None, 'blocked_section'),
    ('https://www.reuters.com/world/europe/russia-strikes-kyiv', 'Reuters', None),
    # A topic word in the article slug is content, not a section.
    ('https://www.reuters.com/world/football-hooligans-clash-with-police', None, None),
])
def test_check_outlet(url, outlet, expected):
    assert check_outlet(url, outlet) == expected


# ── topics ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('text,expected', [
    ('Lando Norris wants ban at Baku Grand Prix', True),
    ('Taylor Swift album breaks box office records', True),
    ('In 1934 a luxury cruise liner caught fire off New Jersey', True),
    ('Man charged with murder after nightclub shooting', True),
    ('Hurricane Polo makes landfall on Mexico coast', True),
    ('Russian drones hit apartments in Kyiv killing 7', False),
    ('Iran vows to clear Arabian Sea of enemy forces in 2026', False),
])
def test_is_off_topic(text, expected):
    assert is_off_topic(text) is expected


# ── GDELT ──────────────────────────────────────────────────────────────────

def gdelt_meta(url='https://www.reuters.com/world/some-story', headline=None, **g):
    base = {
        'is_root_event': '1', 'event_code': '190', 'base_code': '190',
        'num_sources': 3, 'num_articles': 5,
        'actor1_code': 'RUS', 'actor1_country': 'RUS', 'actor1_type': '',
        'actor2_code': 'UKR', 'actor2_country': 'UKR', 'actor2_type': '',
    }
    base.update(g)
    return {'kind': 'gdelt', 'url': url, 'headline': headline, 'gdelt': base}


def test_interstate_military_event_is_kept():
    assert check_gdelt({}, gdelt_meta()) is None


def test_non_root_event_is_rejected():
    assert check_gdelt({}, gdelt_meta(is_root_event='0')) == 'not_root_event'


def test_event_without_actors_is_rejected():
    assert check_gdelt({}, gdelt_meta(actor1_code='', actor2_code='')) == 'no_actors'


def test_criminal_and_police_only_is_rejected():
    meta = gdelt_meta(actor1_code='USACOP', actor1_country='USA', actor1_type='COP',
                      actor2_code='USACRM', actor2_country='USA', actor2_type='CRM', base_code='173')
    assert check_gdelt({}, meta) == 'non_geopolitical_actors'


def test_bare_country_code_does_not_make_domestic_violence_political():
    # GDELT codes a place ("Kansas City") as the state actor USA; a domestic
    # shooting needs an armed-group actor to count.
    meta = gdelt_meta(actor1_code='USA', actor1_country='USA', actor2_code='', base_code='190')
    assert check_gdelt({}, meta) == 'domestic_non_political'


def test_domestic_fighting_with_armed_actor_is_kept():
    meta = gdelt_meta(actor1_code='ETHMIL', actor1_country='ETH', actor1_type='MIL',
                      actor2_code='ETHREB', actor2_country='ETH', actor2_type='REB', base_code='193')
    assert check_gdelt({}, meta) is None


def test_domestic_verbal_conflict_is_rejected_but_interstate_kept():
    domestic = gdelt_meta(actor1_code='DEUGOV', actor1_country='DEU', actor1_type='GOV',
                          actor2_code='DEUOPP', actor2_country='DEU', actor2_type='OPP', base_code='111')
    assert check_gdelt({}, domestic) == 'domestic_verbal_conflict'
    assert check_gdelt({}, gdelt_meta(base_code='138')) is None
    assert check_gdelt({}, gdelt_meta(base_code='112')) is None   # Russia accuses Ukraine


def test_minor_protest_rejected_large_or_opposition_protest_kept():
    small = gdelt_meta(actor1_code='INDLEG', actor1_country='IND', actor1_type='LEG',
                       actor2_code='', base_code='141', num_articles=2)
    assert check_gdelt({}, small) == 'minor_protest'
    opposition = gdelt_meta(actor1_code='INDOPP', actor1_country='IND', actor1_type='OPP',
                            actor2_code='', base_code='141', num_articles=2)
    assert check_gdelt({}, opposition) is None


def test_vague_coercion_code_is_rejected():
    assert check_gdelt({}, gdelt_meta(base_code='171')) == 'vague_event_code'


def test_uncorroborated_single_source_is_rejected_except_armed_fighting():
    thin = gdelt_meta(base_code='163', num_sources=1, num_articles=1)   # sanctions, 1 article
    assert check_gdelt({}, thin) == 'uncorroborated'
    fighting = gdelt_meta(actor1_code='RUSMIL', actor1_type='MIL', num_sources=1, num_articles=1)
    assert check_gdelt({}, fighting) is None


def test_off_topic_headline_rejected_for_domestic_events():
    meta = gdelt_meta(url='https://economictimes.com/news/in-1934-a-luxury-cruise-ship-burned',
                      actor1_code='USAMIL', actor1_country='USA', actor1_type='MIL', actor2_code='')
    assert check_gdelt({}, meta) == 'off_topic'


def test_blocked_outlet_rejected_for_gdelt():
    meta = gdelt_meta(url='https://www.crash.net/f1/news/1105752/1/lando-norris-wants-ban')
    assert check_gdelt({}, meta) == 'blocked_outlet'


# ── NewsAPI ────────────────────────────────────────────────────────────────

def news(text, url='https://www.reuters.com/world/x', outlet='Reuters', stakeholders=''):
    return {'stakeholders': stakeholders}, {'kind': 'news', 'text': text, 'url': url, 'outlet': outlet}


def test_news_needs_an_actor_signal():
    assert check_news(*news('Clashes erupt near the stadium as fighting spreads')) == 'no_geopolitical_actor'
    assert check_news(*news('Troops clash with rebels near the border')) is None
    assert check_news(*news('Sudanese forces clash in the capital')) is None       # demonym
    assert check_news(*news('Clashes reported across Ukraine overnight')) is None  # country name
    assert check_news(*news('Missile strike on Kyiv kills civilians')) is None     # weapon implies an armed actor


def test_off_topic_news_rejected_unless_several_states_involved():
    assert check_news(*news('Football fans clash with police after Nigeria match')) == 'off_topic'
    assert check_news(*news('World Cup host Russia and Ukraine trade strikes',
                            stakeholders='RU,UA')) is None


def test_news_from_blocked_outlet_rejected():
    assert check_news(*news('Troops clash with rebels', url='https://www.skysports.com/x')) == 'blocked_outlet'


# ── ACLED ──────────────────────────────────────────────────────────────────

def acled(**fields):
    return {}, {'kind': 'acled', 'acled': fields}


def test_acled_events_with_fatalities_always_kept():
    assert check_acled(*acled(sub_event_type='Peaceful protest', fatalities='1')) is None


def test_acled_low_signal_sub_types_dropped_without_fatalities():
    assert check_acled(*acled(sub_event_type='Peaceful protest', fatalities='0')) == 'low_signal_acled_event'
    assert check_acled(*acled(event_type='Strategic developments', sub_event_type='Other',
                              fatalities='0')) == 'low_signal_acled_event'


def test_acled_strategic_development_kept_only_with_state_actor():
    kept = acled(event_type='Strategic developments', sub_event_type='Agreement', fatalities='0',
                 actor1='Military Forces of Sudan (2019-)', actor2='Rapid Support Forces')
    assert check_acled(*kept) is None
    dropped = acled(event_type='Strategic developments', sub_event_type='Agreement', fatalities='0',
                    actor1='Unidentified Armed Group', actor2='')
    assert check_acled(*dropped) == 'low_signal_acled_event'


def test_acled_armed_clash_without_fatalities_kept():
    assert check_acled(*acled(event_type='Battles', sub_event_type='Armed clash', fatalities='0')) is None


# ── end to end ─────────────────────────────────────────────────────────────

def test_f1_news_article_is_rejected_by_the_pipeline(app_module):
    crisis = ds.NewsBasedCrisisDetector._extract_crisis_from_article({
        'title': 'Norris wants race ban after Baku Grand Prix clash',
        'description': 'The Formula 1 driver said the clash in Baku was avoidable.',
        'source': {'name': 'Crash.net'},
        'publishedAt': '2026-09-20T10:00:00Z',
        'url': 'https://www.crash.net/f1/news/1105752/norris-baku',
    })
    result = event_pipeline.process_batch([crisis], 'NewsAPI')
    assert result.kept == []
    assert result.rejected[0][0] == 'blocked_outlet'


def test_real_news_story_survives_the_pipeline(app_module):
    crisis = ds.NewsBasedCrisisDetector._extract_crisis_from_article({
        'title': 'Russian missile strike on Kyiv kills civilians - Reuters',
        'description': 'KYIV (Reuters) - Russian forces launched missiles at the capital overnight.',
        'source': {'name': 'Reuters'},
        'publishedAt': '2026-09-20T10:00:00Z',
        'url': 'https://www.reuters.com/world/europe/russian-missile-strike-kyiv',
    })
    [kept] = event_pipeline.process_batch([crisis], 'NewsAPI').kept
    assert kept['title'] == 'Russian missile strike on Kyiv kills civilians'


def test_sample_rows_without_meta_pass_untouched():
    sample = {'id': 'sample_x', 'type': 'conflict', 'title': 'Kyiv Conflict Zone', 'country': 'Ukraine',
              'latitude': 50.45, 'longitude': 30.52, 'severity': 90}
    assert len(event_pipeline.process_batch([sample], 'ACLED').kept) == 1
