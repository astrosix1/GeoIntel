"""
Tests for event_pipeline location handling: canonical countries
(countries.py), point-in-country geometry (geo.py), news placement and the
location stage (location.py).

Modelled on real wrong-country pins: capitals used to mean governments
("Washington sanctions Venezuela" pinned in the US), ambiguous city names
("Victoria" -> Seychelles), and a GDELT Berlin-Moscow diplomacy story
pinned in Miami.
"""
import pytest

import event_pipeline
from event_pipeline import countries, geo
from event_pipeline.location import check_location, resolve_news_location, resolve_geo_fullname


# ── countries ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('UK', 'United Kingdom'), ('Britain', 'United Kingdom'), ('US', 'United States'),
    ('Korea, South', 'South Korea'), ('DPRK', 'North Korea'), ('Burma', 'Myanmar'),
    ('DRC', 'DR Congo'), ('Congo, Democratic Republic of the', 'DR Congo'),
    ("Cote d'Ivoire", 'Ivory Coast'), ('Gaza Strip', 'Palestine'), ('Russian Federation', 'Russia'),
    ('the Netherlands', 'Netherlands'), ('Türkiye', 'Turkey'), ('Kosovo', 'Kosovo'),
])
def test_country_aliases_resolve_to_one_canonical_record(raw, expected):
    assert countries.resolve(raw)['name'] == expected


def test_unknown_names_do_not_resolve():
    assert countries.resolve('Kyiv') is None
    assert countries.resolve('') is None


def test_cameo_codes_resolve_including_legacy_ones():
    assert countries.from_iso3('RUS')['name'] == 'Russia'
    assert countries.from_iso3('ZAR')['name'] == 'DR Congo'


def test_country_code_is_the_topojson_numeric_id():
    assert countries.resolve('Ukraine')['code'] == '804'


def test_short_aliases_only_match_exact_case_in_text():
    names = [countries.by_code(c)['name'] for c, *_ in countries.find_in_text('US forces told us to leave')]
    assert names == ['United States']


def test_demonyms_are_found():
    assert [(countries.by_code(c)['name'], k) for c, _, _, k in countries.find_in_text('Sudanese troops')] == \
        [('Sudan', 'demonym')]


# ── geometry ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('lat,lon,expected', [
    (50.45, 30.52, 'Ukraine'), (55.75, 37.61, 'Russia'), (35.68, 139.65, 'Japan'),
    (65.7, -171.0, 'Russia'),          # Chukotka, east of the antimeridian
    (42.66, 21.16, 'Kosovo'),          # topojson feature without an ISO id
    (30.0, -40.0, None),               # mid-Atlantic
])
def test_country_at(lat, lon, expected):
    code = geo.country_at(lat, lon)
    assert (countries.by_code(code)['name'] if code else None) == expected


def test_coastal_city_counts_as_inside_with_tolerance():
    # Miami sits just offshore at 1:50m resolution.
    us = countries.resolve('United States')['code']
    assert not geo.contains(us, 25.76, -80.19)
    assert geo.point_in_country(25.76, -80.19, us, tolerance_km=25)


def test_fiji_across_the_antimeridian():
    assert geo.point_in_country(-18.14, 178.44, countries.resolve('Fiji')['code'], tolerance_km=25)


def test_distance_to_a_far_country_is_large():
    assert geo.distance_km(countries.resolve('Japan')['code'], 50.45, 30.52, cap_km=500) == 500


# ── news placement ─────────────────────────────────────────────────────────

def place(title, description=''):
    result = resolve_news_location(title, description)
    return (result['country'], result['precision'], result['place']) if result else None


def test_capital_as_government_is_not_the_location():
    assert place('Washington imposes new sanctions on Venezuela') == ('Venezuela', 'country', 'Venezuela')


def test_only_metonymic_capitals_place_at_the_party_acted_upon():
    assert place('Washington warns Tehran against retaliation') == ('Iran', 'country', 'Iran')
    # A real place named alongside wins over the fallback.
    assert place('Washington warns Tehran over Strait of Hormuz')[:2] == ('Iran', 'city')
    assert place('Beijing says it will respond firmly') == ('China', 'country', 'China')


def test_moscow_backed_is_not_moscow():
    assert place('Moscow-backed forces shell Kharkiv overnight')[:2] == ('Ukraine', 'city')


def test_ambiguous_city_needs_its_country_named():
    assert place('Protesters clash with police in Victoria') is None
    assert place('Protesters clash with police in Victoria, Seychelles')[:2] == ('Seychelles', 'city')


def test_target_beats_attacker():
    assert place('Russia strikes Kyiv with drones')[2] == 'Kyiv'
    assert place('Israel strikes Lebanon as tensions rise') == ('Lebanon', 'country', 'Lebanon')


def test_title_country_with_located_city_in_description():
    assert place('Sudan army retakes key positions',
                 'Fighting continued near Khartoum as forces advanced.')[2] == 'Khartoum'


def test_ambiguous_country_name_needs_location_context():
    assert place('Protests in Georgia over foreign agents law')[:2] == ('Georgia', 'country')
    assert place('Jordan scores as tensions ease') is None


def test_country_only_article_is_placed_at_country_precision():
    lat, lon = countries.resolve('Mali')['centroid']
    result = resolve_news_location('Junta in Mali expels UN envoy')
    assert (result['country'], result['precision'], result['lat'], result['lon']) == ('Mali', 'country', lat, lon)


# ── location stage ─────────────────────────────────────────────────────────

def cand(country, lat, lon, **extra):
    return {'id': 'x', 'type': 'conflict', 'title': 'Some event title', 'country': country,
            'latitude': lat, 'longitude': lon, **extra}


def test_stage_normalizes_country_and_sets_code_and_confidence():
    c, meta = cand('UK', 51.5074, -0.1278), {'kind': 'news', 'precision': 'city'}
    assert check_location(c, meta) is None
    assert c['country'] == 'United Kingdom'
    assert meta['country_code'] == '826'
    assert c['location_confidence'] == 82


def test_sample_row_with_a_city_as_country_is_fixed():
    c, meta = cand('Kyiv', 50.45, 30.52), {}
    assert check_location(c, meta) is None
    assert c['country'] == 'Ukraine'


def test_coordinates_outside_claimed_country_rejected_unless_a_party():
    # News claims Ukraine but the point is in Poland; Poland isn't named.
    c, meta = cand('Ukraine', 52.23, 21.01), {'kind': 'news', 'parties': ['804']}
    assert check_location(c, meta) == 'coords_country_mismatch'
    # Poland is named in the article: the country name is corrected.
    c, meta = cand('Ukraine', 52.23, 21.01), {'kind': 'news', 'parties': ['804', '616']}
    assert check_location(c, meta) is None and c['country'] == 'Poland'


def test_offshore_point_near_claimed_country_kept():
    c, meta = cand('Iran', 26.56, 56.26), {'kind': 'news', 'parties': ['364']}   # Strait of Hormuz
    assert check_location(c, meta) is None


def test_country_precision_moves_to_centroid_with_low_confidence():
    c, meta = cand('Mali', 1.0, 1.0), {'kind': 'news', 'precision': 'country'}
    assert check_location(c, meta) is None
    assert [c['latitude'], c['longitude']] == countries.resolve('Mali')['centroid']
    assert c['location_confidence'] == 55


def gdelt_meta(actor1='DEU', actor2='RUS', place='Miami, Florida, United States', alt_geos=(), precision='city'):
    return {'kind': 'gdelt', 'place_full_name': place, 'precision': precision, 'alt_geos': list(alt_geos),
            'gdelt': {'actor1_country': actor1, 'actor2_country': actor2,
                      'actor1_code': actor1, 'actor2_code': actor2,
                      'actor1_name': (countries.from_iso3(actor1) or {}).get('name', ''),
                      'actor2_name': (countries.from_iso3(actor2) or {}).get('name', '')}}


def test_gdelt_location_in_a_non_party_country_is_rejected():
    c = cand('United States', 25.76, -80.19)
    assert check_location(c, gdelt_meta()) == 'geo_actor_mismatch'


def test_gdelt_relocates_to_an_actor_geo_in_a_party_country():
    c = cand('United States', 25.76, -80.19)
    meta = gdelt_meta(alt_geos=[{'type': '4', 'full_name': 'Berlin, Berlin, Germany', 'lat': '52.52', 'lon': '13.405'}])
    assert check_location(c, meta) is None
    assert (c['country'], c['latitude'], meta['place_full_name']) == ('Germany', 52.52, 'Berlin, Berlin, Germany')


def test_gdelt_single_party_relocates_to_its_centroid():
    # An IGO (no country) and Israel, geocoded to New York.
    c = cand('United States', 40.71, -74.0)
    meta = gdelt_meta(actor1='', actor2='ISR', place='New York, New York, United States')
    assert check_location(c, meta) is None
    assert c['country'] == 'Israel' and meta['location_precision'] == 'country'


def test_gdelt_fips_country_with_a_comma_resolves():
    assert resolve_geo_fullname('Seoul, Seoul-t\'ukpyolsi, Korea, South')['name'] == 'South Korea'


def test_gdelt_cameo_title_names_the_relocated_place():
    row = {'id': 'g1', 'type': 'diplomatic', 'title': None, 'country': 'United States',
           'latitude': 25.76, 'longitude': -80.19, 'severity': 20,
           '_meta': {**gdelt_meta(alt_geos=[{'type': '4', 'full_name': 'Berlin, Berlin, Germany',
                                             'lat': '52.52', 'lon': '13.405'}]),
                     'cameo': {'actor1': 'GERMANY', 'actor2': 'RUSSIA', 'event_code': '112'}}}
    row['_meta']['gdelt'].update(actor1_code='DEU', actor2_code='RUS', actor1_name='GERMANY',
                                 actor2_name='RUSSIA', base_code='112', num_sources=3,
                                 num_articles=4, is_root_event='1')
    [kept] = event_pipeline.process_batch([row], 'GDELT').kept
    assert kept['title'] == 'Germany accuses Russia in Berlin, Germany'
