"""
The Government tab: the Factbook's account of the executive, legislature (with seats, elections and women's share), courts,
constitution and parties; how democratic the country is (V-Dem, bundled); who has held the top offices (Wikidata); its
international groupings (Factbook); a plain-language "how power works" (a model reading only the Factbook text); and a short
Wikipedia introduction with attribution. Every group is optional.
"""
from concurrent.futures import ThreadPoolExecutor

from data_sources import wikidata, wikipedia
from data_sources.factbook import FactbookConnector
from services import country_data as bundled
from services.country_power import explain
from services.org_names import describe

FACTBOOK = 'CIA World Factbook'


def build_tab(cc):
    """Everything for the Government tab, or None when no source has anything for the country."""
    out = {'country_code': cc, 'tab': 'government', 'sources': []}
    factbook = FactbookConnector.fetch_profile(cc)
    gov = factbook['government'] if factbook else None
    with ThreadPoolExecutor(max_workers=3) as pool:
        leaders_f = pool.submit(wikidata.leaders, cc)
        intro_f = pool.submit(wikipedia.politics_intro, cc)
        power_f = pool.submit(explain, cc, gov) if gov else None
        leaders, intro = leaders_f.result(), intro_f.result()
        power = power_f.result() if power_f else None
    if gov:
        out['government'] = {k: v for k, v in gov.items() if k != 'memberships'}
        memberships = describe(gov.get('memberships'))
        if memberships:
            out['memberships'] = memberships
        out['sources'].append(FACTBOOK)
    democracy = bundled.democracy(cc)
    if democracy:
        out['democracy'] = democracy
        out['sources'].append(democracy['source'])
    if leaders:
        out['leaders'] = leaders
        out['sources'].append(leaders['source'])
    if power:
        out['power'] = power
        out['sources'].append('Plain-language summary written by an AI model from the Factbook text above')
    if intro:
        out['intro'] = intro
        out['sources'].append('Wikipedia (' + intro['license'] + ')')
    return out if len(out['sources']) else None
