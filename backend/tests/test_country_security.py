"""Security tab: event trend and hotspots (our database), military figures, displacement, travel advice and memberships."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from data_sources import travel_advice as ta
from data_sources.factbook import parse_memberships
from services import country_detail as cd
from services import country_security as cs
from services.org_names import describe


class TestMemberships:
    def test_commas_inside_brackets_do_not_split(self):
        out = parse_memberships('ADB (nonregional member), AfDB (a, b), EU, G-7, UN (permanent member)')
        assert [m['abbr'] for m in out] == ['ADB', 'AfDB', 'EU', 'G-7', 'UN']
        assert out[0]['note'] == 'nonregional member' and out[2]['note'] is None
        assert parse_memberships(None) is None

    def test_known_groups_are_named_and_security_comes_first(self):
        out = describe([{'abbr': 'UN', 'note': None}, {'abbr': 'NATO', 'note': None}, {'abbr': 'XYZ', 'note': None}])
        assert [m['abbr'] for m in out] == ['NATO', 'UN', 'XYZ']
        assert out[0]['kind'] == 'security' and out[0]['name'].startswith('North Atlantic')
        assert out[2]['name'] == 'XYZ' and out[2]['kind'] == 'other'  # unknown abbreviations are never guessed at


class TestTravelAdvice:
    def _page(self, alerts, body='<p>FCDO advises against all travel to X due to danger.</p><p>Other.</p>'):
        return {'details': {'alert_status': alerts, 'reviewed_at': '2026-10-01T10:00:00Z', 'parts': [{'body': body}]}}

    @pytest.fixture(autouse=True)
    def fresh(self):
        with patch('data_sources.travel_advice.cache_get', return_value=None), patch('data_sources.travel_advice.cache_set'):
            yield

    def test_level_summary_and_link(self):
        index = {'links': {'children': [{'details': {'country': {'name': 'Syria', 'slug': 'syria', 'synonyms': []}}}]}}
        pages = {ta.BASE: index, f'{ta.BASE}/syria': self._page(['avoid_all_travel_to_whole_country'])}
        with patch('data_sources.travel_advice._get', side_effect=lambda url: pages.get(url)):
            out = ta.advice('SY')
        assert out['level'] == 3 and out['alerts'][0]['label'].startswith('Advises against all travel')
        assert out['summary'] == ['FCDO advises against all travel to X due to danger.']
        assert out['updated'] == '2026-10-01' and out['url'].endswith('/syria')

    def test_no_alerts_is_level_zero_and_inline_links_do_not_split_sentences(self):
        index = {'links': {'children': [{'details': {'country': {'name': 'USA', 'slug': 'usa', 'synonyms': ['United States']}}}]}}
        body = '<p>FCDO <a href="x">advises against</a> travel to the area.</p>'
        pages = {ta.BASE: index, f'{ta.BASE}/usa': self._page([], body)}
        with patch('data_sources.travel_advice._get', side_effect=lambda url: pages.get(url)):
            out = ta.advice('US')
        assert out['level'] == 0 and out['alerts'] == []
        assert out['summary'] == ['FCDO advises against travel to the area.']

    def test_unknown_country_or_failure_is_none(self):
        with patch('data_sources.travel_advice._get', return_value=None):
            assert ta.advice('SY') is None
        with patch('data_sources.travel_advice._get', return_value={'links': {'children': []}}):
            assert ta.advice('SY') is None


class TestTab:
    @patch('services.country_security.FactbookConnector')
    @patch('services.country_security.unhcr')
    @patch('services.country_security.travel_advice')
    @patch('services.country_security.wb')
    def test_groups_come_from_their_sources_and_missing_ones_are_left_out(self, wbmod, advice, unh, fb):
        wbmod.SOURCE = 'World Bank'
        wbmod.stats.return_value = [{'code': 'MS.MIL.XPND.GD.ZS', 'label': 'Military spending'}]
        advice.advice.return_value = None
        unh.SOURCE = 'UNHCR Refugee Statistics'
        unh.origin_series.return_value = [{'year': 2025, 'refugees': 9}]
        fb.fetch_profile.return_value = {'security': {'terrorist_groups': 'X'}, 'government': {'memberships': [{'abbr': 'NATO', 'note': None}]}}
        out = cs.build_tab('FR')
        assert out['stats'][0]['label'] == 'Military spending' and 'advisory' not in out
        assert out['displacement']['series'][0]['refugees'] == 9
        assert out['memberships'][0]['name'].startswith('North Atlantic') and out['security']['terrorist_groups'] == 'X'

    @patch('services.country_security.FactbookConnector')
    @patch('services.country_security.unhcr')
    @patch('services.country_security.travel_advice')
    @patch('services.country_security.wb')
    def test_nothing_anywhere_is_none(self, wbmod, advice, unh, fb):
        wbmod.stats.return_value = []
        advice.advice.return_value = None
        unh.origin_series.return_value = None
        fb.fetch_profile.return_value = None
        assert cs.build_tab('ZZ') is None


def _event(db_session, days_ago=1, lat=35.0, lon=38.0, **extra):
    values = dict(id=f'sx-{uuid.uuid4().hex[:8]}', type='conflict', title='Clashes', country='Yemen', latitude=lat, longitude=lon,
                  severity=50, source='GDELT', is_active=True, event_kind='physical', source_count=1,
                  date_start=datetime.utcnow() - timedelta(days=days_ago))
    values.update(extra)
    db_session.add(cd.Crisis(**values))
    db_session.commit()
    return values['id']


def test_conflict_picture_has_weekly_trend_and_named_hotspots(app_module, db_session):
    from cache import cache_delete
    cache_delete('country_conflicts:v2:YE')
    for _ in range(3):
        _event(db_session, days_ago=2, lat=35.0, lon=38.0, location_refined_name='Palmyra', severity=70, title='Shelling near the ruins')
    _event(db_session, days_ago=2, lat=33.5, lon=36.3)             # a single report: not a hotspot
    _event(db_session, days_ago=40, lat=35.0, lon=38.0)            # in the trend, not in the 30-day count
    _event(db_session, days_ago=200)                               # outside the trend
    with patch('data_sources.geocoding.NominatimGeocoder.reverse', return_value='Somewhere') as reverse:
        out = cd.build_conflicts('YE')
    assert out['total'] == 4 and len(out['weekly']) == cd.TREND_WEEKS
    assert sum(count for _, count in out['weekly']) == 5
    assert out['weekly'][-1][1] >= 4 or out['weekly'][-2][1] >= 4  # this week or last
    assert [h['name'] for h in out['hotspots']] == ['Palmyra'] and out['hotspots'][0]['count'] == 3
    assert out['hotspots'][0]['headline'] == 'Shelling near the ruins'
    reverse.assert_not_called()  # a refined name was already there
