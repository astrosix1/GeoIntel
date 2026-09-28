"""
Tests for event_pipeline/scoring.py — the two scores:
  severity      = local intensity (event class + casualties + scale)
  global_impact = international significance (drives the critical badge)

The old scores saturated: GDELT's -Goldstein*10 made every "fight" 100
(31% of a live hour was >= 80), news started at 50, and a stabbing and a
missile strike on a capital could both be "critical".
"""
import json
import random
from datetime import datetime

import pytest

import data_sources as ds
import event_pipeline
from event_pipeline import countries
from event_pipeline.scoring import band, parse_fatalities, score, extract_features, merge_features
from models import Crisis, CrisisSource


def code(name):
    return countries.resolve(name)['code']


def features(cls='armed_clash', fatalities=None, parties=('Ukraine',), interstate=False, kind='news',
             strategic=None, escalation=False, verified=False, scale=0):
    return {'kind': kind, 'class': cls, 'fatalities': fatalities, 'scale': scale,
            'parties': sorted(code(p) for p in parties), 'interstate': interstate,
            'escalation': escalation, 'strategic': strategic, 'verified': verified}


# ── bands + parsing ────────────────────────────────────────────────────────

@pytest.mark.parametrize('value,expected', [(100, 'critical'), (80, 'critical'), (79, 'high'), (60, 'high'),
                                            (59, 'elevated'), (35, 'elevated'), (34, 'low'), (0, 'low')])
def test_bands(value, expected):
    assert band(value) == expected


@pytest.mark.parametrize('text,expected', [
    ('Russian Drones Hammer Apartments in Ukraine Killing 7', 7),
    ('At least 12 people were killed in the attack', 12),
    ('Death toll rises to 150 after the strike', 150),
    ('Dozens killed as fighting intensifies', 24),
    ('Two soldiers died at the border', 2),
    ('1,200 civilians killed since the offensive began', 1200),
    ('Talks resume with no casualties reported', None),
])
def test_parse_fatalities(text, expected):
    assert parse_fatalities(text) == expected


# ── severity (local intensity) ─────────────────────────────────────────────

def test_a_gdelt_fight_is_no_longer_automatically_100():
    severity, impact, _ = score(features('armed_clash', kind='gdelt', parties=('Canada',)))
    assert severity == 45
    assert band(impact) == 'low'


def test_severity_rises_with_casualties():
    low, _, _ = score(features('assault', fatalities=0))
    mid, _, _ = score(features('assault', fatalities=30), source_count=3)
    high, _, _ = score(features('assault', fatalities=600), source_count=3)
    assert low < mid < high == 80


def test_severity_caps():
    assert score(features('verbal', fatalities=0))[0] <= 30
    assert score(features('protest'))[0] <= 40
    # A single unverified report can't claim more than 65 however bloody.
    assert score(features('mass_violence', fatalities=1000), source_count=1)[0] == 65
    assert score(features('mass_violence', fatalities=1000, kind='acled', verified=True))[0] == 100


# ── global impact ──────────────────────────────────────────────────────────

def test_interstate_strike_by_a_nuclear_great_power_is_high_but_single_source_capped():
    f = features('aerial', fatalities=7, parties=('Russia', 'Ukraine'), interstate=True)
    _, single, factors = score(f, source_count=1)
    _, widely, _ = score(f, source_count=12)
    assert single == 60                        # single-source cap
    assert band(widely) == 'critical'           # interstate + nuclear party, widely reported
    assert factors['global_impact']['critical_requirements_met'] == ['interstate', 'nuclear_party']


def test_critical_needs_two_strong_signals():
    # Very bloody, widely reported, but domestic: no interstate/nuclear.
    f = features('mass_violence', fatalities=300, parties=('Nigeria',), kind='acled', verified=True)
    severity, impact, _ = score(f, source_count=30)
    assert band(severity) == 'critical'
    assert impact <= 55                          # domestic cap
    assert band(impact) == 'elevated'


def test_mass_casualties_add_international_attention():
    quiet = score(features('assault', fatalities=2, parties=('Nigeria',), kind='acled', verified=True))[1]
    massacre = score(features('assault', fatalities=200, parties=('Nigeria',), kind='acled', verified=True))[1]
    assert massacre >= quiet + 15


def test_verbal_interstate_spat_is_capped():
    f = features('verbal', parties=('Iran', 'United States'), interstate=True)
    assert score(f, source_count=30)[1] <= 50


def test_strategic_location_and_escalation_terms_add():
    base = features('posture', parties=('Iran', 'United States'), interstate=True)
    plain = score(base, source_count=5)[1]
    chokepoint = score({**base, 'strategic': 'Strait of Hormuz'}, source_count=5)[1]
    escalation = score({**base, 'escalation': True}, source_count=5)[1]
    assert chokepoint == plain + 8 and escalation == plain + 10


def test_curated_rows_keep_their_own_severity():
    severity, _, factors = score(features(kind=None), preset_severity=88)
    assert severity == 88 and factors['severity'] == {'preset': 88}


# ── feature extraction ─────────────────────────────────────────────────────

def test_gdelt_features_from_cameo_and_actors():
    meta = {'kind': 'gdelt', 'country_code': code('Ukraine'), 'url': 'https://x.com/a',
            'headline': 'Russian Drones Hammer Apartments in Ukraine Killing 7',
            'gdelt': {'base_code': '195', 'actor1_code': 'RUS', 'actor1_country': 'RUS', 'actor1_type': '',
                      'actor1_name': 'RUSSIA', 'actor2_code': 'UKR', 'actor2_country': 'UKR',
                      'actor2_type': '', 'actor2_name': 'UKRAINE'}}
    f = extract_features({'title': meta['headline'], 'latitude': 50.45, 'longitude': 30.52}, meta)
    assert (f['class'], f['fatalities'], f['interstate']) == ('aerial', 7, True)


def test_acled_features_find_state_forces():
    meta = {'kind': 'acled', 'country_code': code('Sudan'),
            'acled': {'event_type': 'Explosions/Remote violence', 'sub_event_type': 'Air/drone strike',
                      'fatalities': '14', 'actor1': 'Military Forces of Sudan (2019-)',
                      'actor2': 'Rapid Support Forces'}}
    f = extract_features({'title': 'Air/drone strike in El Fasher', 'latitude': 13.6, 'longitude': 25.3}, meta)
    assert (f['class'], f['fatalities'], f['interstate']) == ('aerial', 14, False)


def test_news_class_and_strategic_keyword():
    meta = {'kind': 'news', 'country_code': code('Iran'), 'parties': [code('Iran'), code('United States')],
            'text': 'Iran seizes tanker in the Strait of Hormuz as US warships approach'}
    f = extract_features({'title': 'Iran seizes tanker in Strait of Hormuz', 'type': 'military',
                          'latitude': 26.5, 'longitude': 56.2}, meta)
    assert f['class'] == 'posture' and f['strategic'] == 'Strait of Hormuz' and f['interstate']


def test_merge_features_keeps_the_strongest_evidence():
    a = features('posture', fatalities=None, parties=('Israel',))
    b = features('aerial', fatalities=9, parties=('Lebanon',), interstate=True)
    merged = merge_features(a, b)
    assert merged['class'] == 'aerial' and merged['fatalities'] == 9 and merged['interstate']
    assert set(merged['parties']) == {code('Israel'), code('Lebanon')}


# ── distribution guardrail ─────────────────────────────────────────────────

def test_critical_impact_is_rare_on_a_realistic_mix():
    """A mix shaped like the filtered live feed: mostly diplomatic friction,
    domestic unrest and local fighting, some interstate strikes, few
    widely-reported interstate escalations."""
    rng = random.Random(7)
    mix = (
        [features('verbal', parties=('Iran', 'United States'), interstate=True)] * 60
        + [features('protest', parties=('India',))] * 30
        + [features('armed_clash', fatalities=rng.randint(0, 20), parties=('Ethiopia',), kind='acled',
                    verified=True) for _ in range(50)]
        + [features('aerial', fatalities=rng.randint(0, 15), parties=('Russia', 'Ukraine'), interstate=True)
           for _ in range(40)]
        + [features('mass_violence', fatalities=rng.randint(100, 400), parties=('Sudan',), kind='acled',
                    verified=True) for _ in range(10)]
        + [features('aerial', fatalities=30, parties=('Israel', 'Iran'), interstate=True)] * 10
    )
    source_counts = [1] * 150 + [rng.randint(2, 6) for _ in range(40)] + [12] * 10
    impacts = [score(f, source_count=n)[1] for f, n in zip(mix, source_counts)]
    critical = sum(band(i) == 'critical' for i in impacts) / len(impacts)
    high = sum(band(i) == 'high' for i in impacts) / len(impacts)
    assert critical <= 0.05
    assert high <= 0.25


# ── wired through the pipeline, storage and API ────────────────────────────

@pytest.fixture()
def clean_db(db_session):
    def wipe():
        db_session.query(CrisisSource).delete()
        db_session.query(Crisis).filter(Crisis.id.like('s_%')).delete(synchronize_session=False)
        db_session.commit()
    wipe()
    yield
    wipe()


def news_candidate(id_, title, url):
    return {'id': id_, 'type': 'conflict', 'title': title, 'country': 'Ukraine', 'latitude': 50.45,
            'longitude': 30.52, 'source': 'NewsAPI', 'source_id': url, 'date_start': datetime(2026, 9, 28, 9),
            '_meta': {'kind': 'news', 'url': url, 'outlet': 'Reuters', 'precision': 'city',
                      'parties': [code('Russia'), code('Ukraine')],
                      'text': title}}


def test_pipeline_scores_kept_events_and_records_factors():
    [kept] = event_pipeline.process_batch(
        [news_candidate('s_1', 'Russian missile strike on Kyiv kills 7', 'https://reuters.com/s1')], 'NewsAPI').kept
    assert kept['severity'] == 65 and kept['global_impact'] == 60
    factors = json.loads(kept['scoring_factors'])
    assert factors['inputs']['class'] == 'aerial' and factors['global_impact']['cap'] == 60


def test_merging_reports_raises_global_impact(app_module, db_session, clean_db):
    ds.DataAggregator._upsert_batch(db_session, [
        news_candidate('s_1', 'Russian missile strike on Kyiv kills 7', 'https://reuters.com/s1')], 'NewsAPI')
    db_session.commit()
    first = db_session.get(Crisis, 's_1').global_impact
    for i in range(2, 5):
        ds.DataAggregator._upsert_batch(db_session, [
            news_candidate(f's_{i}', 'Russian missile strike on Kyiv kills 7 people', f'https://site{i}.com/x')],
            'NewsAPI')
        db_session.commit()
    row = db_session.get(Crisis, 's_1')
    assert row.source_count == 4
    assert row.global_impact > first


def test_api_returns_bands_and_sorts_by_global_impact(app_module, client, db_session, clean_db):
    from cache import cache_clear_prefix
    for id_, sev, imp in (('s_local', 90, 30), ('s_global', 50, 85)):
        db_session.add(Crisis(id=id_, type='conflict', title=id_, country='Ukraine', latitude=50.4,
                              longitude=30.5, severity=sev, global_impact=imp, is_active=True, status='active'))
    db_session.commit()
    cache_clear_prefix('crises:')
    body = client.get('/api/crises').get_json()
    ours = [c for c in body['crises'] if c['id'] in ('s_local', 's_global')]
    assert [c['id'] for c in ours] == ['s_global', 's_local']
    assert (ours[0]['impact_band'], ours[1]['severity_band']) == ('critical', 'critical')
    cache_clear_prefix('crises:')
    filtered = client.get('/api/crises?min_impact=80').get_json()['crises']
    assert 's_local' not in [c['id'] for c in filtered]
