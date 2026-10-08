"""
The Security tab: what our own events show (trend, busiest places), military spending and size (World Bank / SIPRI), people
displaced (UNHCR), the UK government's travel advice, and the international groupings the country belongs to (Factbook).
Every group is optional; a source with nothing for a country leaves its group out. The live event picture is added fresh by
services/country_tabs.get_country_tab (it has its own short cache).
"""
from concurrent.futures import ThreadPoolExecutor

from data_sources import travel_advice, unhcr
from data_sources.factbook import FactbookConnector
from services import country_indicators as wb
from services.org_names import describe

MILITARY_STATS = [
    ('MS.MIL.XPND.GD.ZS', 'Military spending', '% of GDP', 2),
    ('MS.MIL.XPND.CD', 'Military spending, in dollars', 'US$', 0, True, True),
    ('MS.MIL.XPND.ZS', 'Share of government spending', '% of government spending', 1),
    ('MS.MIL.TOTL.P1', 'Armed forces personnel', 'people', 0),
    ('MS.MIL.MPRT.KD', 'Arms imports', 'SIPRI trend value', 0, True, True),
    ('MS.MIL.XPRT.KD', 'Arms exports', 'SIPRI trend value', 0, True, True),
]


def build_tab(cc):
    """Everything for the Security tab except the live event counts, or None when no source has anything."""
    out = {'country_code': cc, 'tab': 'security', 'sources': []}
    with ThreadPoolExecutor(max_workers=4) as pool:
        stats_f = pool.submit(wb.stats, cc, MILITARY_STATS)
        advice_f = pool.submit(travel_advice.advice, cc)
        displaced_f = pool.submit(unhcr.origin_series, cc)
        factbook = FactbookConnector.fetch_profile(cc)
        stats, advisory, displaced = stats_f.result(), advice_f.result(), displaced_f.result()
    if stats:
        out['stats'] = stats
        out['sources'].append(wb.SOURCE + ' (military figures: SIPRI)')
    if advisory:
        out['advisory'] = advisory
        out['sources'].append(advisory['source'])
    if displaced:
        out['displacement'] = {'source': unhcr.SOURCE, 'series': displaced}
        out['sources'].append(unhcr.SOURCE)
    if factbook:
        out['security'] = factbook['security']
        memberships = describe(factbook['government'].get('memberships'))
        if memberships:
            out['memberships'] = memberships
        out['sources'].append('CIA World Factbook')
    return out if len(out['sources']) else None
