"""
Tests for event_pipeline/titles.py — cleaning source titles and
synthesizing readable ones, plus the titles stage as wired into the
ACLED, GDELT and NewsAPI connectors.

Before this, ACLED titles were ID codes ("UKR12345"), GDELT titles were
"Unknown actor — conflict event in X", and news headlines kept the outlet
name ("... - Reuters") or were nothing but a live-blog date.
"""
import pytest

import data_sources as ds
import event_pipeline
from event_pipeline.titles import (
    clean_title, choose_title, acled_title, slug_title, gdelt_title, first_sentence, headline_case,
)


def make_row(global_event_id='1000001', source_url='https://example.com/article'):
    """Minimal GDELT export row (see make_row in test_gdelt.py for the
    column layout): an interstate root event, RUSSIA vs UKRAINE, CAMEO
    190, Kyiv — one that passes the relevance rules."""
    fields = [''] * 61
    fields[0] = global_event_id
    fields[5], fields[7], fields[6] = 'RUS', 'RUS', 'RUSSIA'
    fields[15], fields[17], fields[16] = 'UKR', 'UKR', 'UKRAINE'
    fields[25] = '1'
    fields[26], fields[29], fields[30] = '190', '4', '-8.0'
    fields[32], fields[33] = '3', '5'
    fields[52], fields[56], fields[57] = 'Kyiv, Kyiv, Ukraine', '50.4501', '30.5234'
    fields[59], fields[60] = '20260924120000', source_url
    return fields


# ── outlet names ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,outlet,url,expected', [
    ('Russia strikes Kyiv power grid - Reuters', 'Reuters', None, 'Russia strikes Kyiv power grid'),
    ('Russia strikes Kyiv power grid | BBC News', 'BBC News', 'https://www.bbc.co.uk/news/x', 'Russia strikes Kyiv power grid'),
    ('Russia strikes Kyiv power grid — Al Jazeera', None, None, 'Russia strikes Kyiv power grid'),
    # Outlet identified from the article's own domain, not a known list.
    ('Sudan army retakes Omdurman - Times of India', 'Unknown', 'https://timesofindia.indiatimes.com/a', 'Sudan army retakes Omdurman'),
    ('Sudan army retakes Omdurman - Example Daily', 'Example Daily', None, 'Sudan army retakes Omdurman'),
    ('Reuters: Iran summons British ambassador', None, None, 'Iran summons British ambassador'),
    ('Iran summons British ambassador (Reuters)', None, None, 'Iran summons British ambassador'),
    # Stacked labels.
    ('Iran summons British ambassador - World - Reuters', 'Reuters', None, 'Iran summons British ambassador - World'),
])
def test_outlet_names_are_stripped(raw, outlet, url, expected):
    assert clean_title(raw, outlet=outlet, url=url) == expected


def test_hyphenated_names_and_real_content_are_not_mistaken_for_outlets():
    assert clean_title('Russia-Ukraine talks stall over prisoner swap') == 'Russia-Ukraine talks stall over prisoner swap'
    # "Kyiv" is part of the domain kyivindependent.com but is story content.
    assert clean_title('Kyiv: missile strike damages power plant', url='https://kyivindependent.com/x') \
        == 'Kyiv: missile strike damages power plant'


# ── tags and dates ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('BREAKING: Coup attempt reported in Niamey', 'Coup attempt reported in Niamey'),
    ('LIVE UPDATES: Israel strikes targets in Lebanon', 'Israel strikes targets in Lebanon'),
    ('UPDATE 2-Philippines protests Chinese coast guard action', 'Philippines protests Chinese coast guard action'),
    ('Explainer | Why the Strait of Hormuz matters', 'Why the Strait of Hormuz matters'),
    ('September 25, 2026: Ukraine reports drone attacks on Odesa', 'Ukraine reports drone attacks on Odesa'),
    ('Ukraine reports drone attacks on Odesa - Sept. 25, 2026', 'Ukraine reports drone attacks on Odesa'),
    ('Ukraine reports drone attacks on Odesa (25 September 2026)', 'Ukraine reports drone attacks on Odesa'),
    ('Ukraine reports drone attacks on Odesa, 2026-09-25', 'Ukraine reports drone attacks on Odesa'),
    ('Day 945: Ukraine reports drone attacks on Odesa', 'Ukraine reports drone attacks on Odesa'),
])
def test_tags_and_date_fragments_are_stripped(raw, expected):
    assert clean_title(raw) == expected


def test_a_date_inside_the_sentence_is_kept():
    assert clean_title('Clashes erupt on May 5 near the border') == 'Clashes erupt on May 5 near the border'


@pytest.mark.parametrize('raw', [
    'September 25, 2026',
    'Thursday, September 25, 2026',
    '2026-09-25',
    'Russia-Ukraine war live: September 25, 2026',   # nothing left but "Russia-Ukraine war"
    'Israel-Hamas war: live updates',
    'Latest news - Reuters',
    'UKR12345',
    'https://example.com/story',
    'Home',
    '',
    None,
])
def test_unusable_titles_are_rejected(raw):
    assert clean_title(raw, outlet='Reuters') is None


def test_all_caps_headlines_are_recased_keeping_acronyms():
    assert clean_title('NATO AND EU WARN RUSSIA OVER BALTIC INCURSIONS') == \
        'NATO and EU Warn Russia over Baltic Incursions'


def test_long_titles_truncate_on_a_word_boundary():
    title = clean_title('Troops advance ' + 'further ' * 60 + 'into the region')
    assert len(title) <= 200 and title.endswith('…') and ' furth…' not in title


def test_short_synthesized_titles_pass_when_not_strict():
    assert clean_title('Coup in Mali', strict=True) is None  # below the headline minimum
    assert clean_title('Coup in Mali', strict=False) == 'Coup in Mali'


# ── choose_title ───────────────────────────────────────────────────────────

def test_choose_title_falls_back_in_order():
    title, synthesized = choose_title(
        'Russia-Ukraine war live: September 25, 2026 - CNN', outlet='CNN',
        fallbacks=[(None, True), ('Russian drones hit Odesa port overnight, officials said', True)],
    )
    assert title == 'Russian drones hit Odesa port overnight, officials said'
    assert synthesized is True


def test_choose_title_prefers_the_source_title():
    assert choose_title('Iran summons British ambassador - Reuters', outlet='Reuters',
                        fallbacks=[('Something else entirely here', True)]) == \
        ('Iran summons British ambassador', False)


# ── synthesis ──────────────────────────────────────────────────────────────

def test_first_sentence_of_description():
    assert first_sentence('Russian drones hit Odesa overnight. Officials said three were hurt. […]') == \
        'Russian drones hit Odesa overnight'
    assert first_sentence('') is None


def test_acled_title_from_fields():
    event = {'sub_event_type': 'Armed clash', 'location': 'Pokrovsk', 'admin1': 'Donetsk',
             'country': 'Ukraine', 'fatalities': '4'}
    assert acled_title(event) == 'Armed clash in Pokrovsk, Donetsk: 4 killed'
    event.update(fatalities='0', location='Donetsk')
    assert acled_title(event) == 'Armed clash in Donetsk'


@pytest.mark.parametrize('url,expected', [
    ('https://blueprint.ng/breaking-5-miners-killed-others-injured-in-plateau-attack/',
     '5 Miners Killed Others Injured in Plateau Attack'),
    ('https://www.politico.eu/article/germany-russia-johann-wadephul-sergey-lavrov-meeting-un/',
     'Germany Russia Johann Wadephul Sergey Lavrov Meeting UN'),
    ('https://site.com/world/2026/09/25/sudan-army-retakes-omdurman-market.html',
     'Sudan Army Retakes Omdurman Market'),
    # "us" in a slug is the pronoun, not the country: never upper-cased to US.
    ('https://site.com/news/iran-tells-us-to-stay-out-of-gulf-1234567',
     'Iran Tells Us to Stay Out of Gulf'),
    ('https://site.com/news/2559138', None),
    ('https://site.com/index.php?id=5', None),
    ('', None),
])
def test_slug_title(url, expected):
    assert slug_title(url) == expected


def test_gdelt_title_with_both_actors_and_place():
    assert gdelt_title('RUSSIA', 'UKRAINE', '195', 'Kharkiv, Kharkivs\'ka Oblast\', Ukraine') == \
        'Russia carries out air strikes on Ukraine in Kharkiv, Ukraine'


def test_gdelt_title_with_one_actor_or_none():
    assert gdelt_title('POLICE', '', '173', 'Lagos, Lagos, Nigeria') == 'Arrests involving Police in Lagos, Nigeria'
    assert gdelt_title('', '', '183', 'Somalia') == 'Bombing in Somalia'
    assert gdelt_title('', '', '999', 'Somalia') is None


def test_headline_case_keeps_acronyms():
    assert headline_case('UNITED NATIONS SECURITY COUNCIL AND NATO') == 'United Nations Security Council and NATO'


# ── wired into connectors + pipeline ───────────────────────────────────────

def _run(candidates, source):
    return event_pipeline.process_batch(candidates, source).kept


def test_acled_event_gets_a_synthesized_title_not_its_id(app_module):
    parsed = ds.ACLEDConnector._parse_event({
        'data_id': '1', 'event_id_cnty': 'UKR12345', 'event_type': 'Battles',
        'sub_event_type': 'Armed clash', 'location': 'Pokrovsk', 'admin1': 'Donetsk',
        'country': 'Ukraine', 'latitude': '48.28', 'longitude': '37.18', 'fatalities': '4',
        'event_date': '2026-09-20', 'notes': '',
    })
    [kept] = _run([parsed], 'ACLED')
    assert kept['title'] == 'Armed clash in Pokrovsk, Donetsk: 4 killed'
    assert '_meta' not in kept


def test_gdelt_row_prefers_url_slug_then_cameo(app_module):
    with_slug = ds.GDELTConnector._parse_row(make_row(
        source_url='https://blueprint.ng/5-miners-killed-in-plateau-attack/'))
    without_slug = ds.GDELTConnector._parse_row(make_row(
        global_event_id='2', source_url='https://example.com/2559138'))
    # Run separately: they are the same event, so together they'd merge.
    [first] = _run([with_slug], 'GDELT')
    [second] = _run([without_slug], 'GDELT')
    assert first['title'] == '5 Miners Killed in Plateau Attack'
    assert second['title'] == 'Russia uses military force against Ukraine in Kyiv, Ukraine'


def test_news_article_title_is_cleaned(app_module):
    crisis = ds.NewsBasedCrisisDetector._extract_crisis_from_article({
        'title': 'BREAKING: Missile strike on Kyiv kills civilians - Reuters',
        'description': 'KYIV (Reuters) - A missile strike hit the capital.',
        'source': {'name': 'Reuters'},
        'publishedAt': '2026-09-20T10:00:00Z',
        'url': 'https://www.reuters.com/world/kyiv-strike',
    })
    [kept] = _run([crisis], 'NewsAPI')
    assert kept['title'] == 'Missile strike on Kyiv kills civilians'


def test_date_only_news_headline_falls_back_to_description(app_module):
    crisis = ds.NewsBasedCrisisDetector._extract_crisis_from_article({
        'title': 'Russia-Ukraine war live: September 25, 2026 - CNN',
        'description': 'Russian drones struck Odesa port overnight. Officials said three were hurt.',
        'source': {'name': 'CNN'},
        'publishedAt': '2026-09-25T10:00:00Z',
        'url': 'https://cnn.com/live/ukraine-sept-25',
    })
    [kept] = _run([crisis], 'NewsAPI')
    assert kept['title'] == 'Russian drones struck Odesa port overnight'
