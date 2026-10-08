"""
The Migration tab: people moving in (UN DESA migrant stock, 1990-2024), people moving out (the same table read from the other
side), refugees and asylum seekers (UNHCR) and money sent home (World Bank remittances). Every group is optional: a source that
has nothing for a country leaves its group out.
"""
from concurrent.futures import ThreadPoolExecutor

from data_sources import unhcr
from services import country_indicators as wb
from services.country_detail import _migration_table

REMITTANCE_STATS = [
    ('BX.TRF.PWKR.CD.DT', 'Remittances received', 'US$', 0, True, True),
    ('BX.TRF.PWKR.DT.GD.ZS', 'Remittances received, share of the economy', '% of GDP', 1),
    ('BM.TRF.PWKR.CD.DT', 'Remittances sent abroad', 'US$', 0, True, True),
]
FLOW_STATS = [('SM.POP.NETM', 'Net migration (arrivals minus departures)', 'people, 5-year estimate', 0, False)]


def _population_by_year(cc):
    return {year: value for year, value in (wb.series(cc, 'SP.POP.TOTL') or [])}


def _nearest(by_year, year):
    if not by_year:
        return None
    return by_year.get(year) or by_year[min(by_year, key=lambda y: abs(y - year))]


def _share_series(series, population):
    out = []
    for year, value in series:
        pop = _nearest(population, year)
        if pop:
            out.append([year, round(value / pop * 100, 2)])
    return out


def build_un(cc, population):
    """Immigrants and emigrants from the bundled UN DESA table."""
    table = _migration_table()
    row = (table.get('countries') or {}).get(cc)
    if not row:
        return None, None
    latest_pop = _nearest(population, table.get('year', 2024))
    immigrants = None
    if row.get('series'):
        stock = row['series'][-1][1]
        listed = sum(count for _, count in row['origins'])
        immigrants = {
            'year': table.get('year'), 'source': table.get('source'), 'stock': stock, 'series': row['series'],
            'share_of_population': round(stock / latest_pop * 100, 1) if latest_pop else None,
            'share_series': _share_series(row['series'], population),
            'origins': [{'country_code': code, 'count': count, 'percent': round(count / stock * 100, 1) if stock else None}
                        for code, count in row['origins']],
            'other_count': max(stock - listed, 0),
        }
    emigrants = None
    em = row.get('emigrants') or {}
    if em.get('series'):
        stock = em['series'][-1][1]
        listed = sum(count for _, count in em['destinations'])
        emigrants = {
            'year': table.get('year'), 'source': table.get('source'), 'stock': stock, 'series': em['series'],
            'share_of_population': round(stock / latest_pop * 100, 1) if latest_pop else None,
            'destinations': [{'country_code': code, 'count': count, 'percent': round(count / stock * 100, 1) if stock else None}
                             for code, count in em['destinations']],
            'other_count': max(stock - listed, 0),
        }
    return immigrants, emigrants


def build_refugees(cc):
    """UNHCR: refugees and asylum seekers the country hosts, and people who have fled it or are displaced inside it."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        hosted_f = pool.submit(unhcr.hosted_series, cc)
        origin_f = pool.submit(unhcr.origin_series, cc)
        hosted, origin = hosted_f.result(), origin_f.result()
    if not hosted and not origin:
        return None
    out = {'source': unhcr.SOURCE}
    with ThreadPoolExecutor(max_workers=2) as pool:
        by_origin_f = pool.submit(unhcr.hosted_by_origin, cc, hosted[-1]['year']) if hosted else None
        by_dest_f = pool.submit(unhcr.abroad_by_destination, cc, origin[-1]['year']) if origin else None
        by_origin = by_origin_f.result() if by_origin_f else None
        by_dest = by_dest_f.result() if by_dest_f else None
    if hosted:
        out['hosted'] = {'latest': hosted[-1], 'series': hosted, 'by_origin': by_origin}
    if origin:
        out['from_here'] = {'latest': origin[-1], 'series': origin, 'by_destination': by_dest}
    return out


def build_tab(cc):
    """Everything for the Migration tab, or None when no source has anything for the country."""
    out = {'country_code': cc, 'tab': 'migration', 'sources': []}
    population = _population_by_year(cc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        refugees_f = pool.submit(build_refugees, cc)
        stats_f = pool.submit(wb.stats, cc, REMITTANCE_STATS + FLOW_STATS)
        immigrants, emigrants = build_un(cc, population)
        refugees, stats = refugees_f.result(), stats_f.result()
    if immigrants:
        out['immigrants'] = immigrants
        out['sources'].append(immigrants['source'])
    if emigrants:
        out['emigrants'] = emigrants
    if refugees:
        out['refugees'] = refugees
        out['sources'].append(refugees['source'])
    if stats:
        out['stats'] = stats
        out['sources'].append(wb.SOURCE)
    return out if (immigrants or emigrants or refugees or stats) else None
