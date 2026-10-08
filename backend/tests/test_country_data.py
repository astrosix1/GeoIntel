"""The bundled country datasets (HDI, electricity mix, minerals) read from backend/data/country."""
from services import country_data as cd


def test_hdi_has_value_tier_rank_and_series():
    jp = cd.hdi('JP')
    assert 0.9 < jp['value'] < 1 and jp['tier'] == 'Very high'
    assert 1 <= jp['rank'] <= jp['of'] and len(jp['series']) > 20
    assert cd.hdi('ZZ') is None


def test_hdi_ranks_are_ordered_by_value():
    assert cd.hdi('NO')['rank'] < cd.hdi('JP')['rank'] < cd.hdi('NE')['rank']
    assert cd.hdi('NE')['tier'] == 'Low'


def test_energy_mix_is_sorted_and_shares_are_sensible():
    fr = cd.energy('FR')
    assert fr['mix'][0]['name'] == 'Nuclear'
    assert [m['percent'] for m in fr['mix']] == sorted((m['percent'] for m in fr['mix']), reverse=True)
    assert 0 < fr['low_carbon_share'] <= 100 and fr['generation_twh'] > 0
    assert cd.energy('ZZ') is None


def test_minerals_list_critical_first_with_rank_and_world_share():
    cd_minerals = cd.minerals('CD')['items']
    assert cd_minerals[0]['critical'] is True
    tantalum = next(m for m in cd_minerals if m['commodity'] == 'Tantalum')
    assert tantalum['rank'] == 1 and tantalum['world_share'] > 30
    criticals = [m['critical'] for m in cd_minerals]
    assert criticals == sorted(criticals, reverse=True)
    assert cd.minerals('ZZ') is None
