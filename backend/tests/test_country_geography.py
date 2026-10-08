"""Geography tab: Factbook geography parsers, live hazards by country, the tab's groups."""
import json
from pathlib import Path
from unittest.mock import patch

from data_sources.factbook import parse_borders, parse_land_use, parse_profile
from services import country_geography as cg

FIX = Path(__file__).parent / 'fixtures' / 'factbook'


def geo(name):
    return parse_profile(json.loads((FIX / f'{name}.json').read_text(encoding='utf-8')))['geography']


class TestParsers:
    def test_borders_with_lengths_largest_first(self):
        out = parse_borders('Andorra 55 km; Belgium 556 km; Spain 646 km; Luxembourg 69 km')
        assert [(b['name'], b['km']) for b in out] == [('Spain', 646.0), ('Belgium', 556.0), ('Luxembourg', 69.0), ('Andorra', 55.0)]
        assert parse_borders(None) is None and parse_borders('none') is None

    def test_notes_in_brackets_do_not_break_a_border(self):
        out = parse_borders('Canada 8,891 km (includes 2,477 km with Alaska); Mexico 3,111 km')
        assert out[0] == {'name': 'Canada', 'km': 8891.0}

    def test_land_use_reads_the_shares_and_marks_the_sub_items(self):
        node = {'agricultural land': {'text': '52.5% (2023 est.)'}, 'agricultural land: arable land': {'text': 'arable land: 31.4% (2023 est.)'},
                'forest': {'text': '31.7% (2023 est.)'}, 'other': {'text': '15.8% (2023 est.)'}}
        out = parse_land_use(node)
        assert [(i['label'], i['percent'], i['sub']) for i in out['items']] == [
            ('Agricultural land', 52.5, False), ('Arable land', 31.4, True), ('Forest', 31.7, False), ('Other', 15.8, False)]
        assert out['as_of'] == 2023 and parse_land_use({}) is None

    def test_real_file_gives_area_borders_elevation_and_water(self):
        fr = geo('fr')
        assert fr['area']['total'].startswith('643,801') and fr['area']['comparative'].startswith('slightly more than four times')
        assert fr['borders']['total'] == '3,956 km' and fr['borders']['countries'][0] == {'name': 'Spain', 'km': 646.0}
        assert fr['elevation']['highest'] == 'Mont Blanc 4,810' and fr['coastline'] == '4,853 km'
        assert fr['water_withdrawal']['industrial'].startswith('16.641') and fr['natural_hazards'].startswith('metropolitan France')

    def test_a_landlocked_country_says_so(self):
        assert 'landlocked' in geo('ng')['coastline']


class TestHazards:
    def _feed(self):
        return {'source': 'gdacs.org', 'storms': [
            {'name': 'A', 'hazard': 'Flood', 'alert_level': 'Green', 'affected_countries': ['France'], 'country': ''},
            {'name': 'B', 'hazard': 'Wildfire', 'alert_level': 'Red', 'affected_countries': [], 'country': 'France'},
            {'name': 'C', 'hazard': 'Flood', 'alert_level': 'Red', 'affected_countries': ['Spain'], 'country': ''}]}

    def test_matches_by_country_name_and_puts_the_worst_alert_first(self):
        with patch('services.weather.get_active_storms', return_value=self._feed()):
            out = cg.active_hazards('FR')
        assert [h['name'] for h in out['items']] == ['B', 'A']

    def test_none_active_is_an_empty_list_not_missing(self):
        with patch('services.weather.get_active_storms', return_value={'storms': []}):
            assert cg.active_hazards('FR')['items'] == []

    def test_a_failing_feed_is_none(self):
        with patch('services.weather.get_active_storms', side_effect=RuntimeError('down')):
            assert cg.active_hazards('FR') is None


class TestTab:
    @patch('services.country_geography.active_hazards', return_value={'items': [], 'source': 'gdacs.org'})
    @patch('services.country_geography.wikipedia')
    @patch('services.country_geography.wb')
    @patch('services.country_geography.FactbookConnector')
    def test_groups_and_sources(self, fb, wbmod, wp, _hazards):
        fb.fetch_profile.return_value = parse_profile(json.loads((FIX / 'fr.json').read_text(encoding='utf-8')))
        wbmod.SOURCE = 'World Bank'
        wbmod.stats.return_value = [{'code': 'AG.LND.TOTL.K2', 'label': 'Land area'}]
        wp.geography_intro.return_value = {'license': 'CC BY-SA 4.0', 'extract': 'x'}
        out = cg.build_tab('FR')
        assert out['geography']['borders']['total'] == '3,956 km' and out['stats'][0]['label'] == 'Land area'
        assert out['hazards']['items'] == [] and 'Wikipedia (CC BY-SA 4.0)' in out['sources']

    @patch('services.country_geography.active_hazards', return_value=None)
    @patch('services.country_geography.wikipedia')
    @patch('services.country_geography.wb')
    @patch('services.country_geography.FactbookConnector')
    def test_nothing_anywhere_is_none(self, fb, wbmod, wp, _hazards):
        fb.fetch_profile.return_value = None
        wbmod.stats.return_value = []
        wp.geography_intro.return_value = None
        assert cg.build_tab('ZZ') is None
