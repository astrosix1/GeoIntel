"""
Tests for duplicate handling (event_pipeline/dedup.py), merging into stored
events (DataAggregator._store_event), provenance (crisis_sources) and
expiry of stale events (DataAggregator.expire_stale).

Before this, one GDELT article became a cluster of pins (186 events from 60
URLs in one live file), the same story from different outlets each got its
own row, and nothing was ever deactivated.
"""
from datetime import datetime, timedelta

import pytest

import data_sources as ds
import event_pipeline
from event_pipeline import dedup, geo, countries
from models import Crisis, CrisisSource, CrisisSnapshot

NOW = datetime(2026, 9, 28, 12, 0, 0)


def news(id_, title, url, lat=50.45, lon=30.52, country='Ukraine', outlet='Reuters', type_='conflict',
         when=NOW, precision='city', source='NewsAPI'):
    return {
        'id': id_, 'type': type_, 'title': title, 'country': country, 'latitude': lat, 'longitude': lon,
        'severity': 60, 'confidence': 75, 'date_start': when, 'source': source, 'source_id': url,
        '_meta': {'precision': precision, 'url': url, 'outlet': outlet},
    }


@pytest.fixture()
def clean_db(db_session):
    def wipe():
        db_session.query(CrisisSource).delete()
        db_session.query(CrisisSnapshot).filter(CrisisSnapshot.crisis_id.like('t_%')).delete(synchronize_session=False)
        db_session.query(Crisis).filter(Crisis.id.like('t_%')).delete(synchronize_session=False)
        db_session.commit()
    wipe()
    yield
    wipe()


# ── similarity + matching ──────────────────────────────────────────────────

def test_title_similarity_weighs_places_double():
    a = dedup.title_tokens('Russian missile strike hits Kyiv apartment block')
    b = dedup.title_tokens('Missile strike on Kyiv apartment building kills three')
    c = dedup.title_tokens('Farmers protest fuel prices in Lagos')
    assert dedup.similarity(a, b) > 0.35
    assert dedup.similarity(a, c) == 0


def test_type_families():
    assert dedup.type_family('conflict') == dedup.type_family('military') == 'armed_conflict'
    assert dedup.type_family('diplomatic') != dedup.type_family('conflict')


# ── within a batch ─────────────────────────────────────────────────────────

def test_one_article_coded_many_times_becomes_one_event():
    url = 'https://www.politico.eu/article/germany-russia-wadephul-lavrov-meeting-un/'
    rows = [news(f't_g{i}', 'Germany Russia Wadephul Lavrov Meeting UN', url, lat=52.52, lon=13.405,
                 country='Germany', type_='diplomatic', source='GDELT') for i in range(18)]
    result = event_pipeline.process_batch(rows, 'GDELT')
    assert len(result.kept) == 1
    assert result.merged == 17
    assert result.kept[0]['source_count'] == 1          # one URL -> one source
    assert result.report.to_dict()['sources']['GDELT']['merged'] == 17


def test_same_story_from_two_outlets_is_one_event_with_two_sources():
    rows = [
        news('t_ap', 'Russian missile strike hits Kyiv apartment block', 'https://apnews.com/a', outlet='AP'),
        news('t_rt', 'Missile strike on Kyiv apartment building kills three - Reuters',
             'https://reuters.com/b', when=NOW + timedelta(hours=3)),
    ]
    result = event_pipeline.process_batch(rows, 'NewsAPI')
    assert len(result.kept) == 1
    assert result.kept[0]['source_count'] == 2
    assert {s['url_key'] for s in result.sources[0]} == {'https://apnews.com/a', 'https://reuters.com/b'}


def test_different_events_in_the_same_city_stay_separate():
    rows = [
        news('t_1', 'Russian missile strike hits Kyiv apartment block', 'https://x.com/1'),
        news('t_2', 'Protesters rally in Kyiv against corruption law', 'https://x.com/2', type_='civil_unrest'),
        news('t_3', 'Ukraine drone attack sparks fire at Kyiv power plant', 'https://x.com/3',
             when=NOW + timedelta(days=4)),
    ]
    assert len(event_pipeline.process_batch(rows, 'NewsAPI').kept) == 3


def test_best_report_becomes_the_primary():
    gdelt = news('t_g', None, 'https://x.com/g', source='GDELT')
    gdelt['_meta']['fallback_titles'] = [('Armed clashes involving Rebels in Kyiv, Ukraine', False)]  # synthesized
    rows = [gdelt, news('t_n', 'Russian forces clash with defenders on Kyiv outskirts', 'https://reuters.com/n')]
    [kept] = event_pipeline.process_batch(rows, 'mixed').kept
    assert kept['id'] == 't_n'


# ── against the database ───────────────────────────────────────────────────

def store(db_session, rows, source='NewsAPI'):
    result = ds.DataAggregator._upsert_batch(db_session, rows, source)
    db_session.commit()
    return result


def test_later_report_merges_into_the_stored_event(app_module, db_session, clean_db):
    first = store(db_session, [news('t_ap', 'Russian missile strike hits Kyiv apartment block', 'https://apnews.com/a')])
    db_session.add(CrisisSnapshot(crisis_id='t_ap', severity=60, recorded_at=NOW))
    db_session.commit()
    second = store(db_session, [news('t_rt', 'Missile strike on Kyiv apartment building kills three',
                                     'https://reuters.com/b', when=NOW + timedelta(hours=5))])

    assert first.stored['inserted'] == 1 and second.stored['merged'] == 1
    assert db_session.get(Crisis, 't_rt') is None                    # no second pin
    row = db_session.get(Crisis, 't_ap')
    assert row.source_count == 2 and row.is_active
    assert db_session.query(CrisisSnapshot).filter_by(crisis_id='t_ap').count() == 1  # history kept
    assert db_session.query(CrisisSource).filter_by(crisis_id='t_ap').count() == 2


def test_report_seen_again_by_url_merges_even_with_a_new_id(app_module, db_session, clean_db):
    store(db_session, [news('t_a', 'Russian missile strike hits Kyiv apartment block', 'https://apnews.com/a')])
    store(db_session, [news('t_b', 'Totally different headline wording here', 'https://apnews.com/a/?utm_source=x')])
    assert db_session.get(Crisis, 't_b') is None
    assert db_session.get(Crisis, 't_a').source_count == 1


def test_merge_upgrades_precision_but_not_a_worse_title(app_module, db_session, clean_db):
    store(db_session, [news('t_c', 'Russian forces clash with defenders near Kyiv', 'https://reuters.com/c',
                            precision='country')])
    # Same story (titles nearly identical), better location, lower-priority source.
    gdelt = news('t_d', 'Russian Forces Clash with Defenders near Kyiv Outskirts', 'https://y.com/d',
                 source='GDELT', lat=50.46, lon=30.53, precision='point')
    store(db_session, [gdelt], source='GDELT')
    assert db_session.get(Crisis, 't_d') is None
    row = db_session.get(Crisis, 't_c')
    assert row.location_precision == 'point'
    assert row.title == 'Russian forces clash with defenders near Kyiv'


def test_same_id_seen_again_revives_and_refreshes(app_module, db_session, clean_db):
    store(db_session, [news('t_e', 'Russian missile strike hits Kyiv apartment block', 'https://apnews.com/e')])
    row = db_session.get(Crisis, 't_e')
    row.is_active = False
    row.last_seen_at = NOW - timedelta(days=10)
    db_session.commit()
    result = store(db_session, [news('t_e', 'Russian missile strike hits Kyiv apartment block', 'https://apnews.com/e')])
    assert result.stored['updated'] == 1
    db_session.refresh(row)
    assert row.is_active and row.last_seen_at > NOW - timedelta(days=1)


def test_crises_from_different_connectors_in_one_sync_merge(app_module, db_session, clean_db):
    acled = news('t_acled', 'Armed clash in Kyiv, Kyiv City: 4 killed', None, source='ACLED', precision='point')
    acled['_meta'].pop('url')
    store(db_session, [acled], source='ACLED')
    store(db_session, [news('t_news', 'Armed clash in Kyiv leaves four dead', 'https://reuters.com/k')])
    row = db_session.get(Crisis, 't_acled')
    assert db_session.get(Crisis, 't_news') is None
    assert row.source_count == 2 and row.title == 'Armed clash in Kyiv, Kyiv City: 4 killed'


# ── expiry ─────────────────────────────────────────────────────────────────

def add_row(db_session, id_, source, last_seen, **extra):
    db_session.add(Crisis(id=id_, type='conflict', title='Row ' + id_, country='Ukraine', latitude=50.45,
                          longitude=30.52, source=source, last_seen_at=last_seen, is_active=True, **extra))


def test_expire_stale_by_source_ttl_with_exemptions(app_module, db_session, clean_db):
    add_row(db_session, 't_gdelt_old', 'GDELT', NOW - timedelta(days=4))
    add_row(db_session, 't_gdelt_new', 'GDELT', NOW - timedelta(days=1))
    add_row(db_session, 't_news_5d', 'NewsAPI', NOW - timedelta(days=5))
    add_row(db_session, 't_lang_old', 'NEWS_API_SPANISH', NOW - timedelta(days=9))
    add_row(db_session, 't_curated', 'CURATED', NOW - timedelta(days=90))
    add_row(db_session, 't_verified', 'GDELT', NOW - timedelta(days=90), is_verified=True)
    add_row(db_session, 't_upcoming', 'NewsAPI', NOW - timedelta(days=90), status='upcoming')
    db_session.commit()

    assert ds.DataAggregator.expire_stale(db_session, now=NOW) == 2
    db_session.commit()
    active = {r.id for r in db_session.query(Crisis).filter(Crisis.id.like('t_%'), Crisis.is_active == True)}  # noqa: E712
    assert active == {'t_gdelt_new', 't_news_5d', 't_curated', 't_verified', 't_upcoming'}


# ── geometry regression found while testing this phase ─────────────────────

def test_canberra_is_in_australia():
    # world-atlas gives the Ashmore and Cartier Islands Australia's id too;
    # the loader used to keep only the islands.
    assert geo.country_at(-35.28, 149.13) == countries.resolve('Australia')['code']
