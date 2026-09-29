"""
Tests for GDELTConnector (Phase 6 of the compendious-tool roadmap) —
a free, real, no-key alternative/addition to ACLED, added after ACLED's own
myACLED access system turned out to gate real API reads behind a
Research-tier/licensed account. GDELT's raw event export is a fixed
61-column tab-separated file with no header; these tests build minimal
realistic rows (only the columns GDELTConnector actually reads varied per
test) rather than depending on the real network.
"""
from unittest.mock import patch, MagicMock

import pytest

import data_sources as ds
from models import Actor


def make_row(
    global_event_id='1000001',
    actor1_name='UNITED STATES',
    actor1_type1='',
    actor2_name='RUSSIA',
    actor2_type1='',
    event_code='190',       # root '19' FIGHT
    quad_class='4',
    goldstein='-8.0',
    num_sources='3',
    num_articles='5',
    action_geo_fullname='Kyiv, Kyiv, Ukraine',
    action_geo_lat='50.4501',
    action_geo_long='30.5234',
    date_added='20260924120000',
    source_url='https://example.com/article',
):
    fields = [''] * 61
    fields[0] = global_event_id
    fields[6] = actor1_name
    fields[12] = actor1_type1
    fields[16] = actor2_name
    fields[22] = actor2_type1
    fields[26] = event_code
    fields[29] = quad_class
    fields[30] = goldstein
    fields[32] = num_sources
    fields[33] = num_articles
    fields[52] = action_geo_fullname
    fields[56] = action_geo_lat
    fields[57] = action_geo_long
    fields[59] = date_added
    fields[60] = source_url
    return fields


@pytest.fixture(autouse=True)
def clean_actors(db_session):
    db_session.query(Actor).delete()
    db_session.commit()
    ds.NewsBasedCrisisDetector._actor_name_patterns = None
    yield
    db_session.query(Actor).delete()
    db_session.commit()
    ds.NewsBasedCrisisDetector._actor_name_patterns = None


def test_quad_class_1_and_2_are_filtered_out(app_module):
    for qc in ('1', '2'):
        assert ds.GDELTConnector._parse_row(make_row(quad_class=qc)) is None


def test_quad_class_3_and_4_are_kept(app_module):
    for qc in ('3', '4'):
        crisis = ds.GDELTConnector._parse_row(make_row(quad_class=qc))
        assert crisis is not None


def test_business_actor_on_either_side_is_rejected(app_module):
    """Real motivating example: a Qualcomm/Apple patent-licensing story was
    CAMEO-coded as coercion between 'COMPANIES' and 'CHINA' — QuadClass 4,
    a mapped event type, real geo — passing every filter that existed
    before this one. A business/corporate actor (BUS/MNC) on either side is
    the real, data-verified signal that the row isn't actually geopolitical
    (see GDELT_NONSTATE_ACTOR_TYPES)."""
    assert ds.GDELTConnector._parse_row(
        make_row(actor1_name='COMPANIES', actor1_type1='BUS', actor2_name='CHINA')
    ) is None
    assert ds.GDELTConnector._parse_row(
        make_row(actor1_name='CHINA', actor2_name='APPLE', actor2_type1='MNC')
    ) is None


def test_state_actor_with_blank_type_code_still_passes(app_module):
    """A real state actor referenced by its own name/country code (e.g.
    'CANADA', 'TURKEY') has NO Actor*Type1Code populated at all in real
    GDELT data — confirmed live (400 of 670 actor-type slots blank across a
    335-row real sample). A positive GOV/MIL allow-list would have wrongly
    rejected rows like this one; the blank-type default must still pass."""
    crisis = ds.GDELTConnector._parse_row(
        make_row(actor1_name='CANADA', actor1_type1='', actor2_name='ISRAEL', actor2_type1='')
    )
    assert crisis is not None


def test_government_or_police_actor_still_passes(app_module):
    crisis = ds.GDELTConnector._parse_row(
        make_row(actor1_name='POLICE', actor1_type1='COP', actor2_name='MINISTRY', actor2_type1='GOV')
    )
    assert crisis is not None


def test_known_cameo_root_codes_map_to_real_crisis_types(app_module):
    cases = {
        '140': 'civil_unrest',  # PROTEST
        '150': 'military',      # EXHIBIT FORCE POSTURE
        '180': 'conflict',      # ASSAULT
        '190': 'conflict',      # FIGHT
        '200': 'conflict',      # MASS VIOLENCE
        '100': 'diplomatic',    # DEMAND
    }
    for event_code, expected_type in cases.items():
        crisis = ds.GDELTConnector._parse_row(make_row(event_code=event_code, quad_class='4'))
        assert crisis['type'] == expected_type, event_code


def test_unmapped_cameo_root_code_is_skipped(app_module):
    # Root '99' doesn't exist in the real CAMEO scheme / GDELT_TYPE_MAP.
    assert ds.GDELTConnector._parse_row(make_row(event_code='990', quad_class='4')) is None


def test_severity_derived_from_goldstein_not_a_constant(app_module):
    harsh = ds.GDELTConnector._parse_row(make_row(goldstein='-10.0'))
    mild = ds.GDELTConnector._parse_row(make_row(goldstein='-1.0'))
    assert harsh['severity'] == 100
    assert mild['severity'] == 10
    assert harsh['severity'] > mild['severity']


def test_severity_clamps_to_zero_for_cooperative_goldstein(app_module):
    # Edge case: a QuadClass 3/4 row with an unusually positive Goldstein
    # score must not produce a negative severity.
    crisis = ds.GDELTConnector._parse_row(make_row(goldstein='5.0'))
    assert crisis['severity'] == 0


def test_confidence_derived_from_real_num_sources(app_module):
    low = ds.GDELTConnector._parse_row(make_row(num_sources='1'))
    high = ds.GDELTConnector._parse_row(make_row(num_sources='8'))
    assert high['confidence'] > low['confidence']
    assert 50 <= low['confidence'] <= 95
    assert 50 <= high['confidence'] <= 95


def test_country_parsed_from_last_comma_segment_of_geo_fullname(app_module):
    crisis = ds.GDELTConnector._parse_row(
        make_row(action_geo_fullname='Antananarivo, Antananarivo, Madagascar')
    )
    assert crisis['country'] == 'Madagascar'


def test_country_level_geo_fullname_with_no_comma(app_module):
    crisis = ds.GDELTConnector._parse_row(make_row(action_geo_fullname='Ukraine'))
    assert crisis['country'] == 'Ukraine'


def test_missing_geo_fullname_is_skipped(app_module):
    assert ds.GDELTConnector._parse_row(make_row(action_geo_fullname='')) is None


def test_zero_zero_placeholder_geo_is_skipped(app_module):
    # GDELT's own placeholder for "no real geo resolved" — must not be
    # treated as a real pin at (0, 0).
    crisis = ds.GDELTConnector._parse_row(
        make_row(action_geo_lat='0', action_geo_long='0')
    )
    assert crisis is None


def test_crisis_id_uses_real_global_event_id(app_module):
    crisis = ds.GDELTConnector._parse_row(make_row(global_event_id='987654321'))
    assert crisis['id'] == 'gdelt_987654321'


def test_crime_blotter_urls_are_flagged_not_filtered(app_module, caplog):
    # Per explicit instruction: local crime stories are ambiguous (a real
    # war-crimes story could share the same "/crime/"/"arrested" wording),
    # so they stay visible — only a log line marks them for later review.
    import logging
    with caplog.at_level(logging.INFO, logger='data_sources'):
        crisis = ds.GDELTConnector._parse_row(
            make_row(source_url='https://example.com/crime/2026/09/24/woman-arrested-in-crash')
        )
    assert crisis is not None
    assert any('possibly-offtopic' in r.message for r in caplog.records)


def test_stakeholders_matched_against_real_actor_roster(app_module, db_session):
    db_session.add_all([
        Actor(id='US', name='United States', category='STATE', latitude=38, longitude=-97),
        Actor(id='RU', name='Russia', category='STATE', latitude=60, longitude=90),
    ])
    db_session.commit()

    crisis = ds.GDELTConnector._parse_row(make_row(actor1_name='UNITED STATES', actor2_name='RUSSIA'))
    assert set(crisis['stakeholders'].split(',')) == {'US', 'RU'}


def test_title_uses_both_real_actors_and_real_cameo_verb(app_module):
    crisis = ds.GDELTConnector._parse_row(
        make_row(actor1_name='UNITED STATES', actor2_name='RUSSIA', event_code='190')
    )
    assert crisis['title'] == 'United States fights Russia'


def test_title_falls_back_to_country_when_actor2_missing(app_module):
    crisis = ds.GDELTConnector._parse_row(
        make_row(actor1_name='PROTESTER', actor2_name='', event_code='140',
                 action_geo_fullname='Cairo, Cairo, Egypt')
    )
    assert crisis['title'] == 'Protester protests against Egypt'


def test_title_falls_back_to_generic_when_actor1_missing(app_module):
    # event_code='140' (PROTEST, root 14) rather than make_row's violent
    # default root — a blank actor1 under a violent root (18/19/20) is
    # rejected outright by GDELT_BLANK_ACTOR_VIOLENT_ROOTS, tested
    # separately below; this test is only about the title fallback shape.
    crisis = ds.GDELTConnector._parse_row(
        make_row(actor1_name='', actor2_name='', event_code='140', action_geo_fullname='France')
    )
    assert crisis['title'] == 'Conflict-related event in France'
    assert 'Unknown actor' not in crisis['title']


def test_source_url_is_stored_on_the_crisis(app_module):
    crisis = ds.GDELTConnector._parse_row(make_row(source_url='https://example.com/real-article'))
    assert crisis['source_url'] == 'https://example.com/real-article'


def test_short_row_is_skipped_not_a_crash(app_module):
    assert ds.GDELTConnector._parse_row(['4']) is None


# ── Off-topic filtering (GDELT_OFFTOPIC_URL_SIGNALS) ─────────────────────
# Grounded in a real, live-confirmed failure: a Deep Purple album/tour
# announcement (URL had no "/music/" path segment, just these slug words)
# produced 74 fabricated "country X fights country Y" crisis records.

def test_entertainment_path_segment_is_filtered(app_module):
    row = make_row(source_url='https://torontosun.com/entertainment/celebrity/some-star-story')
    assert ds.GDELTConnector._parse_row(row) is None


def test_sports_path_segment_is_filtered(app_module):
    row = make_row(source_url='https://example.com/sports/recap/team-wins')
    assert ds.GDELTConnector._parse_row(row) is None


def test_deep_purple_style_slug_words_are_filtered(app_module):
    row = make_row(
        source_url='https://ilovebobfm.com/2026/09/24/deep-purple-releases-splat-album-with-box-set-plans-86-show-world-tour/'
    )
    assert ds.GDELTConnector._parse_row(row) is None


def test_ordinary_news_url_is_not_filtered(app_module):
    row = make_row(source_url='https://www.reuters.com/world/europe/some-real-story-2026-09-24/')
    assert ds.GDELTConnector._parse_row(row) is not None


def test_offtopic_filter_is_case_insensitive(app_module):
    row = make_row(source_url='https://EXAMPLE.com/ENTERTAINMENT/some-story')
    assert ds.GDELTConnector._parse_row(row) is None


# ── Per-source-URL fan-out cap (GDELT_MAX_CRISES_PER_SOURCE_URL) ─────────
# Grounded in the same real finding: dozens of rows citing one identical
# source_url almost always means GDELT invented permutations from a single
# article, not dozens of genuinely distinct real events.

def _crisis(id, source_url, severity, confidence=50):
    return {'id': id, 'source_url': source_url, 'severity': severity, 'confidence': confidence}


def test_fanout_cap_keeps_all_when_under_the_limit(app_module):
    n = ds.GDELT_MAX_CRISES_PER_SOURCE_URL
    crises = [_crisis(f'c{i}', 'https://example.com/a', 50) for i in range(n)]
    result = ds.GDELTConnector._cap_fanout_per_source_url(crises)
    assert len(result) == n


def test_fanout_cap_trims_to_the_limit_when_over(app_module):
    crises = [_crisis(f'c{i}', 'https://example.com/a', 50) for i in range(20)]
    result = ds.GDELTConnector._cap_fanout_per_source_url(crises)
    assert len(result) == ds.GDELT_MAX_CRISES_PER_SOURCE_URL


def test_fanout_cap_keeps_the_highest_confidence_ones(app_module):
    # Tie-break is confidence, NOT severity — confirmed live that sorting
    # by severity instead systematically inflates the surviving dataset's
    # severity distribution (see the function's own docstring for the real
    # before/after numbers). Severity is deliberately uniform here so a
    # regression back to severity-sorting wouldn't accidentally pass.
    n = ds.GDELT_MAX_CRISES_PER_SOURCE_URL
    crises = [_crisis(f'c{i}', 'https://example.com/a', 50, confidence=i) for i in range(20)]  # confidence 0..19
    result = ds.GDELTConnector._cap_fanout_per_source_url(crises)
    kept_confidences = sorted(c['confidence'] for c in result)
    assert kept_confidences == list(range(20 - n, 20))  # the top n by confidence


def test_fanout_cap_applies_independently_per_url(app_module):
    crises = (
        [_crisis(f'a{i}', 'https://example.com/a', 50) for i in range(10)]
        + [_crisis(f'b{i}', 'https://example.com/b', 50) for i in range(2)]
    )
    result = ds.GDELTConnector._cap_fanout_per_source_url(crises)
    from_a = [c for c in result if c['source_url'] == 'https://example.com/a']
    from_b = [c for c in result if c['source_url'] == 'https://example.com/b']
    assert len(from_a) == ds.GDELT_MAX_CRISES_PER_SOURCE_URL
    assert len(from_b) == 2


def test_fanout_cap_passes_through_crises_with_no_source_url(app_module):
    crises = [{'id': 'no-url', 'source_url': None, 'severity': 50, 'confidence': 50}]
    result = ds.GDELTConnector._cap_fanout_per_source_url(crises)
    assert len(result) == 1


def test_get_recent_timestamps_derives_correct_real_url_pattern(app_module):
    fake_response = MagicMock()
    fake_response.text = (
        "12345 abc123 http://data.gdeltproject.org/gdeltv2/20260924120000.export.CSV.zip\n"
        "67890 def456 http://data.gdeltproject.org/gdeltv2/20260924120000.mentions.CSV.zip\n"
        "11111 ghi789 http://data.gdeltproject.org/gdeltv2/20260924120000.gkg.csv.zip\n"
    )
    fake_response.raise_for_status = lambda: None

    with patch('data_sources.requests.get', return_value=fake_response) as mock_get:
        timestamps = ds.GDELTConnector._get_recent_timestamps()

    mock_get.assert_called_once_with(ds.GDELT_LASTUPDATE_URL, timeout=10)
    assert timestamps == ['20260924120000', '20260924114500', '20260924113000', '20260924111500']


def test_fetch_event_rows_returns_empty_on_network_failure_not_a_crash(app_module):
    with patch('data_sources.requests.get', side_effect=Exception('network down')):
        assert ds.GDELTConnector._fetch_event_rows('20260924120000') == []


def test_fetch_recent_events_returns_empty_when_lastupdate_fails(app_module):
    with patch('data_sources.requests.get', side_effect=Exception('network down')):
        assert ds.GDELTConnector.fetch_recent_events() == []


def test_fetch_recent_events_dedups_across_overlapping_windows(app_module):
    # The same GlobalEventID appearing in more than one of the 4 fetched
    # files (real overlap since GDELT's windows aren't perfectly disjoint
    # in practice) must only produce one crisis record.
    row = make_row(global_event_id='555')
    with patch.object(ds.GDELTConnector, '_get_recent_timestamps', return_value=['t1', 't2']), \
         patch.object(ds.GDELTConnector, '_fetch_event_rows', return_value=[row]):
        crises = ds.GDELTConnector.fetch_recent_events()

    assert len(crises) == 1
    assert crises[0]['id'] == 'gdelt_555'


# ── Self-referential and generic-actor-name rejection ────────────────────
# Both verified against real live GDELT data before implementing (same
# discipline as GDELT_NONSTATE_ACTOR_TYPES): every one of 7 real
# self-referential rows and 8 real generic-actor-name rows sampled was
# confirmed non-geopolitical noise (a drug-policy statement, a grand-jury
# indictment, a home-security product review, a community business gala —
# zero real geopolitical false positives in either sample).

def test_self_referential_actor_pair_is_rejected(app_module):
    assert ds.GDELTConnector._parse_row(
        make_row(actor1_name='UNITED STATES', actor2_name='UNITED STATES')
    ) is None


def test_different_actors_still_pass(app_module):
    assert ds.GDELTConnector._parse_row(
        make_row(actor1_name='UNITED STATES', actor2_name='RUSSIA')
    ) is not None


@pytest.mark.parametrize('generic_name', [
    'COMPANY', 'Companies', 'business', 'CORPORATION',
    'ATTORNEY', 'Prison', 'judge', 'CRIMINAL',
])
def test_generic_actor_name_is_rejected_regardless_of_side_or_case(app_module, generic_name):
    assert ds.GDELTConnector._parse_row(make_row(actor1_name=generic_name)) is None
    assert ds.GDELTConnector._parse_row(make_row(actor2_name=generic_name)) is None


def test_generic_actor_name_does_not_reject_similar_real_words(app_module):
    # 'Businessman' etc. shouldn't accidentally match on a substring —
    # GDELT_GENERIC_ACTOR_NAMES is an exact (case-insensitive) match.
    assert ds.GDELTConnector._parse_row(make_row(actor1_name='BUSINESSMAN')) is not None


@pytest.mark.parametrize('similar_word', ['Judiciary', 'Prisoner', 'Attorneys', 'Police'])
def test_generic_actor_extension_does_not_reject_similar_or_deliberately_kept_words(app_module, similar_word):
    # 'Judiciary'/'Prisoner'/'Attorneys' shouldn't substring-match the new
    # attorney/prison/judge entries; 'Police' was live-sampled alongside
    # the new additions and confirmed to contain real geopolitical stories
    # (Haiti gang violence, etc.) — deliberately NOT added to the set.
    assert ds.GDELTConnector._parse_row(make_row(actor1_name=similar_word)) is not None


# ── Extended off-topic URL signals ────────────────────────────────────────
# Added from real, confirmed-live false positives: a wrestlezone.com
# pro-wrestling story and a hindustantimes.com /astrology/horoscope/ page
# both cleared every gate that existed before this.

@pytest.mark.parametrize('url', [
    'https://www.wrestlezone.com/news/1664491-some-wrestling-story',
    'https://www.hindustantimes.com/astrology/horoscope/chinese-horoscope-today',
])
def test_newly_added_offtopic_signals_are_filtered(app_module, url):
    assert ds.GDELTConnector._parse_row(make_row(source_url=url)) is None


# ── Real location-confidence derivation (_parse_geo_fullname) ────────────

def test_country_only_geo_gets_low_confidence(app_module):
    row = make_row(action_geo_fullname='Qatar')
    crisis = ds.GDELTConnector._parse_row(row)
    assert crisis['location_confidence'] == 55


def test_admin1_level_geo_gets_medium_confidence(app_module):
    row = make_row(action_geo_fullname='Texas, United States')
    crisis = ds.GDELTConnector._parse_row(row)
    assert crisis['location_confidence'] == 70


def test_city_level_geo_gets_high_confidence(app_module):
    row = make_row(action_geo_fullname='Kyiv, Kyiv, Ukraine')
    crisis = ds.GDELTConnector._parse_row(row)
    assert crisis['location_confidence'] == 85


# ── Per-event-cluster fan-out cap (GDELT_MAX_CRISES_PER_EVENT_CLUSTER) ────
# Grounded in real findings: 574 rows for one real event across 217
# distinct source URLs (the per-URL cap doesn't help there), and 202 rows
# sharing the exact same coordinate on one day.

from datetime import datetime as _dt  # noqa: E402


def _cluster_crisis(id, country, date_start, lat, lon, severity, source_url=None, confidence=50):
    return {
        'id': id, 'country': country, 'date_start': date_start,
        'latitude': lat, 'longitude': lon, 'severity': severity,
        'source_url': source_url, 'confidence': confidence,
    }


def test_event_cluster_cap_keeps_all_when_under_the_limit(app_module):
    n = ds.GDELT_MAX_CRISES_PER_EVENT_CLUSTER
    day = _dt(2026, 9, 24, 12, 0, 0)
    crises = [_cluster_crisis(f'c{i}', 'United States', day, 38.9, -77.0, 50) for i in range(n)]
    result = ds.GDELTConnector._cap_fanout_per_event_cluster(crises)
    assert len(result) == n


def test_event_cluster_cap_trims_to_the_limit_and_keeps_highest_confidence(app_module):
    # Tie-break is confidence, NOT severity — same reasoning/measurement as
    # the per-source-url cap's equivalent test above. Severity is
    # deliberately uniform here so a regression back to severity-sorting
    # wouldn't accidentally pass.
    day = _dt(2026, 9, 24, 12, 0, 0)
    crises = [_cluster_crisis(f'c{i}', 'United States', day, 38.9, -77.0, 50, confidence=i) for i in range(20)]
    result = ds.GDELTConnector._cap_fanout_per_event_cluster(crises)
    n = ds.GDELT_MAX_CRISES_PER_EVENT_CLUSTER
    assert len(result) == n
    assert sorted(c['confidence'] for c in result) == list(range(20 - n, 20))


def test_event_cluster_cap_applies_independently_per_cluster(app_module):
    day = _dt(2026, 9, 24, 12, 0, 0)
    n = ds.GDELT_MAX_CRISES_PER_EVENT_CLUSTER
    crises = (
        [_cluster_crisis(f'us{i}', 'United States', day, 38.9, -77.0, 50) for i in range(20)]
        + [_cluster_crisis(f'ru{i}', 'Russia', day, 55.75, 37.6, 50) for i in range(2)]
    )
    result = ds.GDELTConnector._cap_fanout_per_event_cluster(crises)
    from_us = [c for c in result if c['country'] == 'United States']
    from_ru = [c for c in result if c['country'] == 'Russia']
    assert len(from_us) == n
    assert len(from_ru) == 2


def test_event_cluster_cap_passes_through_rows_missing_geo_or_date(app_module):
    crises = [{'id': 'no-geo', 'country': None, 'date_start': None, 'latitude': None, 'longitude': None, 'severity': 50}]
    result = ds.GDELTConnector._cap_fanout_per_event_cluster(crises)
    assert len(result) == 1


# ── _clean_article_title ──────────────────────────────────────────────────

def test_clean_title_strips_known_source_suffix(app_module):
    title = 'Trump Aides Seek to Jump Start Diplomacy With Iran - The New York Times'
    assert ds._clean_article_title(title, source_name='The New York Times') == \
        'Trump Aides Seek to Jump Start Diplomacy With Iran'


def test_clean_title_strips_plausible_unknown_suffix(app_module):
    title = 'US, Iran Discussing Phased End to War - Reports'
    assert ds._clean_article_title(title) == 'US, Iran Discussing Phased End to War'


def test_clean_title_does_not_strip_a_real_sentence_clause(app_module):
    title = 'A Title - With a real sentence. That has punctuation'
    assert ds._clean_article_title(title) == title


@pytest.mark.parametrize('date_title', [
    'September 28, 2026', '9/28/2026', '28 September 2026', '2026-09-28',
])
def test_clean_title_rejects_date_only_titles(app_module, date_title):
    assert ds._clean_article_title(date_title) is None


def test_clean_title_rejects_empty_or_none(app_module):
    assert ds._clean_article_title('') is None
    assert ds._clean_article_title(None) is None


def test_clean_title_passes_through_normal_titles(app_module):
    title = 'Real headline with no suffix at all'
    assert ds._clean_article_title(title) == title


# ── ACLED title builder ────────────────────────────────────────────────────

def test_acled_title_uses_real_actors_and_event_type(app_module):
    event = {'actor1': 'Military Forces of Russia (2000-)', 'actor2': 'Military Forces of Ukraine (2019-)', 'event_type': 'Battles'}
    assert ds.ACLEDConnector._build_title(event, 'Ukraine') == \
        'Battles: Military Forces of Russia (2000-) vs Military Forces of Ukraine (2019-)'


def test_acled_title_falls_back_to_country_when_no_actor2(app_module):
    event = {'actor1': 'Protesters (Kenya)', 'event_type': 'Protests'}
    assert ds.ACLEDConnector._build_title(event, 'Kenya') == 'Protests: Protesters (Kenya) in Kenya'


def test_acled_title_falls_back_when_no_actors_at_all(app_module):
    event = {'event_type': 'Riots'}
    assert ds.ACLEDConnector._build_title(event, 'Nigeria') == 'Riots in Nigeria'


# ── Frequency-based location matching (_find_most_mentioned_city) ────────

def test_most_mentioned_city_wins_not_first_mentioned(app_module):
    # Real, confirmed failure mode of the old "first city mentioned wins"
    # logic: a headline naming the acting party's city first, even though
    # the story is really about a different place mentioned more often.
    text = 'washington warns beijing over taipei deployment near taipei as taipei prepares'
    assert ds.NewsBasedCrisisDetector._find_most_mentioned_city(text) == 'taipei'


def test_most_mentioned_city_ties_broken_by_earliest_position(app_module):
    text = 'washington and beijing both issued statements today'
    assert ds.NewsBasedCrisisDetector._find_most_mentioned_city(text) == 'washington'


def test_most_mentioned_city_returns_none_for_no_match(app_module):
    assert ds.NewsBasedCrisisDetector._find_most_mentioned_city('no known city here at all') is None


# ── Blank-actor + violent-root rejection (GDELT_BLANK_ACTOR_VIOLENT_ROOTS) ─
# Grounded in a real finding: of 1,110 rows sharing the generic blank-actor
# fallback title, root 19 (FIGHT) averaged severity 99.7 (366 rows) and root
# 18 (ASSAULT) averaged 92.6 (31 rows) — a live 15-row sample of root-19
# rows found 13 confirmed non-geopolitical (school lockdown, bus crash,
# building fire, etc.). Roots 10-17 are deliberately untouched.

def test_blank_actor_under_violent_root_is_rejected(app_module):
    for event_code in ('180', '190', '200'):  # ASSAULT, FIGHT, MASS VIOLENCE
        row = make_row(actor1_name='', actor2_name='', event_code=event_code, quad_class='4')
        assert ds.GDELTConnector._parse_row(row) is None, event_code


def test_blank_actor_under_diplomatic_root_still_passes(app_module):
    # Roots 10-17 are lower-severity and weren't part of the confirmed-noise
    # finding — a blank actor here must not be newly rejected.
    row = make_row(actor1_name='', actor2_name='', event_code='140', quad_class='4')
    crisis = ds.GDELTConnector._parse_row(row)
    assert crisis is not None


def test_named_actor_under_violent_root_still_passes(app_module):
    # Only a BLANK actor1 combined with a violent root is rejected — a real,
    # named actor (even alone) must still pass.
    row = make_row(actor1_name='UKRAINE', actor2_name='', event_code='190', quad_class='4')
    assert ds.GDELTConnector._parse_row(row) is not None


# ── Per-(title, day) syndication fan-out cap ──────────────────────────────
# Grounded in a real finding: one Australian PM/AI story was republished
# verbatim across 21+ distinct *.com.au regional-newspaper domains, each its
# own source_url (evading the per-URL cap) and often its own nearby
# coordinate (evading the per-cluster cap too).

def _title_day_crisis(id, title, date_start, confidence=50):
    return {'id': id, 'title': title, 'date_start': date_start, 'confidence': confidence}


def test_title_day_cap_keeps_all_when_under_the_limit(app_module):
    n = ds.GDELT_MAX_CRISES_PER_EVENT_CLUSTER
    day = _dt(2026, 9, 24, 12, 0, 0)
    crises = [_title_day_crisis(f'c{i}', 'Regional Paper Runs Same AP Story', day) for i in range(n)]
    result = ds.GDELTConnector._cap_fanout_per_title_day(crises)
    assert len(result) == n


def test_title_day_cap_trims_to_the_limit_and_keeps_highest_confidence(app_module):
    day = _dt(2026, 9, 24, 12, 0, 0)
    crises = [
        _title_day_crisis(f'c{i}', 'Regional Paper Runs Same AP Story', day, confidence=i)
        for i in range(20)
    ]
    result = ds.GDELTConnector._cap_fanout_per_title_day(crises)
    n = ds.GDELT_MAX_CRISES_PER_EVENT_CLUSTER
    assert len(result) == n
    assert sorted(c['confidence'] for c in result) == list(range(20 - n, 20))


def test_title_day_cap_excludes_the_generic_blank_actor_fallback_title(app_module):
    # These share one uninformative title across genuinely distinct real
    # events (confirmed live: 888 distinct source_urls behind it) — capping
    # by shared title here would wrongly delete real, different data.
    day = _dt(2026, 9, 24, 12, 0, 0)
    crises = [
        _title_day_crisis(f'c{i}', 'Conflict-related event in France', day)
        for i in range(20)
    ]
    result = ds.GDELTConnector._cap_fanout_per_title_day(crises)
    assert len(result) == 20


def test_title_day_cap_passes_through_rows_missing_a_date(app_module):
    crises = [{'id': 'no-date', 'title': 'Some Title', 'date_start': None, 'confidence': 50}]
    result = ds.GDELTConnector._cap_fanout_per_title_day(crises)
    assert len(result) == 1


# ── Retroactive content-quality detectors (for cleanup_duplicate_crises.py) ─
# These reconstruct the ingestion-time checks from an already-stored title/
# analysis string, since the raw actor fields aren't kept once a row becomes
# a Crisis — used by the one-time DB cleanup script, not at ingestion time.

def test_retroactive_self_referential_detection_matches_ingestion(app_module):
    # This exact actor pair is rejected at ingestion (see
    # test_self_referential_actor_pair_is_rejected) — the retroactive
    # detector must independently catch the same real pattern from the
    # title text alone, for rows that predate that ingestion check.
    assert ds.GDELTConnector._parse_row(
        make_row(actor1_name='HAMAS', actor2_name='HAMAS', event_code='190')
    ) is None
    title = ds.GDELTConnector._build_title('HAMAS', 'HAMAS', '19', 'Gaza')
    assert ds.GDELTConnector._is_self_referential_title(title) is True


def test_retroactive_self_referential_detection_rejects_real_different_actors(app_module):
    title = ds.GDELTConnector._build_title('RUSSIA', 'UKRAINE', '19', 'Ukraine')
    assert ds.GDELTConnector._is_self_referential_title(title) is False


def test_retroactive_self_referential_detection_covers_legacy_single_actor_format(app_module):
    # A legacy title format no longer produced by _build_title today
    # (confirmed live: 122 rows still carry it) — self-referential here
    # means the single actor IS the country.
    assert ds.GDELTConnector._is_self_referential_title(
        'UNITED STATES — conflict event in United States'
    ) is True
    assert ds.GDELTConnector._is_self_referential_title(
        'CHINA — conflict event in Russia'
    ) is False


# ── Demonym-form self-referential detection (GDELT_DEMONYM_TO_COUNTRY) ────
# Grounded in a real, live-DB scan: repeated confirmed examples like
# "Philippine criticizes Philippines", "Japanese fights Japan" (sev 100),
# and "Africa fights South Africa" (a GDELT truncation quirk, not a real
# demonym, but confirmed self-referential in every sampled occurrence).

@pytest.mark.parametrize('actor1,actor2', [
    ('PHILIPPINE', 'PHILIPPINES'),
    ('JAPANESE', 'JAPAN'),
    ('AUSTRALIAN', 'AUSTRALIA'),
    ('SAUDI', 'SAUDI ARABIA'),
    ('AFRICA', 'SOUTH AFRICA'),
])
def test_demonym_form_self_referential_pair_is_rejected_at_ingestion(app_module, actor1, actor2):
    assert ds.GDELTConnector._parse_row(
        make_row(actor1_name=actor1, actor2_name=actor2)
    ) is None


def test_demonym_normalization_does_not_reject_real_different_countries(app_module):
    # 'Saudi'/'Saudi Arabia' are the same country; 'Saudi'/'Iran' are not.
    assert ds.GDELTConnector._parse_row(
        make_row(actor1_name='SAUDI', actor2_name='IRAN')
    ) is not None


def test_retroactive_demonym_self_referential_detection(app_module):
    title = ds.GDELTConnector._build_title('PHILIPPINE', 'PHILIPPINES', '11', 'Philippines')
    assert ds.GDELTConnector._is_self_referential_title(title) is True

    title2 = ds.GDELTConnector._build_title('JAPANESE', 'JAPAN', '19', 'Japan')
    assert ds.GDELTConnector._is_self_referential_title(title2) is True


def test_retroactive_demonym_detection_does_not_flag_real_distinct_countries(app_module):
    # A naive substring/fuzzy check would wrongly flag these — Russia and
    # Ukraine are two real, distinct countries in a real conflict.
    title = ds.GDELTConnector._build_title('RUSSIA', 'UKRAINE', '19', 'Ukraine')
    assert ds.GDELTConnector._is_self_referential_title(title) is False

    title2 = ds.GDELTConnector._build_title('NORTH KOREA', 'SOUTH KOREA', '13', 'North Korea')
    assert ds.GDELTConnector._is_self_referential_title(title2) is False


def test_retroactive_generic_actor_name_detection(app_module):
    title = ds.GDELTConnector._build_title('COMPANY', 'FRANCE', '11', 'France')
    assert ds.GDELTConnector._starts_with_generic_actor_name(title) is True


def test_retroactive_generic_actor_name_detection_ignores_real_names(app_module):
    title = ds.GDELTConnector._build_title('FRANCE', 'GERMANY', '11', 'France')
    assert ds.GDELTConnector._starts_with_generic_actor_name(title) is False


def test_retroactive_blank_actor_violent_root_detection(app_module):
    title = ds.GDELTConnector._build_title('', '', '19', 'Brazil')
    analysis = 'GDELT-monitored event (CAMEO 190), reported via https://example.com/a'
    assert ds.GDELTConnector._is_blank_actor_violent_root(title, analysis) is True


def test_retroactive_blank_actor_diplomatic_root_is_not_flagged(app_module):
    title = ds.GDELTConnector._build_title('', '', '14', 'Brazil')
    analysis = 'GDELT-monitored event (CAMEO 140), reported via https://example.com/a'
    assert ds.GDELTConnector._is_blank_actor_violent_root(title, analysis) is False


def test_retroactive_blank_actor_detection_requires_the_generic_title(app_module):
    # A named-actor title must never trip this check even under a violent
    # root — only the exact blank-actor fallback title qualifies.
    title = ds.GDELTConnector._build_title('UKRAINE', 'RUSSIA', '19', 'Ukraine')
    analysis = 'GDELT-monitored event (CAMEO 190), reported via https://example.com/a'
    assert ds.GDELTConnector._is_blank_actor_violent_root(title, analysis) is False
