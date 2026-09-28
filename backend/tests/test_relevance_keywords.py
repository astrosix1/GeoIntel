"""
Regression tests for keyword matching in news-derived crises.

Keywords used to be tested as raw substrings, so 'ai' matched "said"
(ordinary quotes became technology stories), 'war' matched "software",
"towards" and "Warsaw" (severity 80), and "heart attack" counted as an
attack. Matching is now word-boundary (event_pipeline.keywords) with an
idiom exclusion list (config/event_filters.json -> phrase_exclusions).
"""
import data_sources as ds
from event_pipeline.keywords import has_keyword, find_keywords, strip_excluded_phrases


def _article(title, description=''):
    return {
        'title': title,
        'description': description,
        'source': {'name': 'Test Wire'},
        'publishedAt': '2026-01-01T00:00:00Z',
        'url': 'https://example.com/' + title.lower().replace(' ', '-'),
    }


def extract(title, description=''):
    return ds.NewsBasedCrisisDetector._extract_crisis_from_article(_article(title, description))


# ── keyword helper ─────────────────────────────────────────────────────────

def test_substrings_inside_words_do_not_match():
    assert not has_keyword('she said the software update ships towards warsaw', ['ai', 'war'])
    assert not has_keyword('farmers tested the soil in las vegas', ['oil', 'gas'])


def test_whole_words_and_inflections_match():
    assert has_keyword('the war continues', ['war'])
    assert has_keyword('airstrikes hit the city as rebels attacked', ['attack'])
    assert has_keyword('protesters were protesting', ['protest'])
    assert has_keyword('two strikes overnight', ['strike'])
    assert has_keyword('AI export controls tightened', ['ai'])


def test_multi_word_phrases_match_with_any_spacing():
    assert has_keyword('a peace   deal was reached', ['peace deal'])
    assert not has_keyword('peace was reached', ['peace deal'])


def test_find_keywords_returns_the_keywords_that_hit():
    assert set(find_keywords('missile strike kills two', ['missile', 'war', 'killed'])) == {'missile'}


def test_idioms_are_stripped_before_matching():
    text = strip_excluded_phrases('heart attack survivor wins price war with rival grocer')
    assert not has_keyword(text, ['attack', 'war'])


# ── end to end through _extract_crisis_from_article ───────────────────────

def test_said_is_not_a_technology_story():
    # 'ai' in "said" used to classify this as technology and accept it.
    assert extract('Taylor Swift said her new album will arrive in Washington next week') is None


def test_software_towards_warsaw_is_not_a_war():
    assert extract('Software update rolls out towards Warsaw users') is None


def test_heart_attack_is_not_an_attack():
    assert extract('Heart attack survivor runs London marathon') is None


def test_real_conflict_story_still_detected():
    crisis = extract('Missile strike on Kyiv kills civilians')
    assert crisis is not None
    assert crisis['type'] == 'conflict'
    assert crisis['country'] == 'Ukraine'


def test_warsaw_is_not_war_for_scoring():
    # 'warsaw' used to hit the 'war' severity weight (80). Severity is now
    # scored from the event class, which for this story is a protest.
    from event_pipeline.scoring import extract_features
    crisis = extract('Farmers protest new rules in Warsaw')
    assert crisis['type'] == 'civil_unrest'
    assert extract_features(crisis, {'kind': 'news', 'text': crisis['title']})['class'] == 'protest'
