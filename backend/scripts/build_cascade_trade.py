"""Build backend/data/cascade/trade.json: for each country and each commodity group the cascade needs, how much it imports and from
whom, from the UN Comtrade public preview API (no key; goods imports, annual, all modes of transport, by partner).

Usage: python scripts/build_cascade_trade.py [--limit N] [--resume PATH]

The preview returns up to 500 rows a call and is rate-limited, so this makes one call per country and commodity group, politely
(a few threads, a pause, retries with back-off), and keeps a resume file so an interrupted run carries on. For each country and
group it takes the newest of 2022, 2023 and 2021 that has data (2022 is the best covered year). Only the top partners are kept:
the app needs shares, not the whole table. Output records the source, licence and the year of every entry.
"""
import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = 'https://comtradeapi.un.org/public/v1/preview/C/A/HS'
REFERENCE = 'https://comtradeapi.un.org/files/v1/app/reference/'
YEARS = (2022, 2023, 2021)
TOP_PARTNERS = 12
WORKERS = 1            # one call at a time: the preview has a call-volume quota, so slow and steady
PAUSE = 1.0
OUT = Path(__file__).resolve().parent.parent / 'data' / 'cascade' / 'trade.json'

# key -> (label, HS code). Chapter-level codes are two digits, headings four, subheadings six.
COMMODITIES = {
    'crude_oil': ('Crude oil', '2709'),
    'oil_products': ('Refined oil products', '2710'),
    'gas': ('Natural gas and LNG', '2711'),
    'coal': ('Coal', '2701'),
    'cereals': ('Cereals (wheat, maize, rice, barley)', '10'),
    'veg_oils': ('Vegetable oils (sunflower, palm, soy)', '15'),
    'fertilizers': ('Fertilizers', '31'),
    'iron_ore': ('Iron ore', '2601'),
    'copper': ('Copper', '74'),
    'aluminium': ('Aluminium', '76'),
    'chips': ('Integrated circuits (chips)', '8542'),
}

# Comtrade's own code for Taiwan is "Other Asia, nes".
PARTNER_OVERRIDES = {490: 'TW'}
_lock = threading.Lock()


class QuotaExceeded(Exception):
    def __init__(self, wait):
        super().__init__(f'quota exceeded, replenished in {wait}s')
        self.wait = wait


def fetch_json(url, tries=5):
    """The JSON at a URL, retrying with back-off. A 403 "Out of call volume quota" is not retried here: it raises QuotaExceeded with the
    wait the API asks for (Retry-After), so the caller can pause the whole run until the quota is back."""
    delay = 2.0
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'GeoIntel data build'}), timeout=40) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 403 and 'quota' in (e.reason or '').lower():
                raise QuotaExceeded(int(e.headers.get('Retry-After') or 3600)) from e
            if attempt == tries - 1:
                print(f'  gave up on {url[-90:]}: {e}', file=sys.stderr)
                return None
        except Exception as e:
            if attempt == tries - 1:
                print(f'  gave up on {url[-90:]}: {e}', file=sys.stderr)
                return None
        time.sleep(delay)
        delay *= 2
    return None


def reference():
    reporters = {r['reporterCode']: r['reporterCodeIsoAlpha2'] for r in fetch_json(REFERENCE + 'Reporters.json')['results']
                 if r.get('reporterCodeIsoAlpha2') and not r.get('isGroup')}
    partners = {p['PartnerCode']: p.get('PartnerCodeIsoAlpha2') for p in fetch_json(REFERENCE + 'partnerAreas.json')['results']
                if p.get('PartnerCodeIsoAlpha2') and not p.get('isGroup')}
    partners.update(PARTNER_OVERRIDES)
    return reporters, partners


def one(reporter_code, hs, partners):
    """{'year', 'total', 'shares': {iso: percent of the total}} for the newest year with data, or None."""
    for year in YEARS:
        time.sleep(PAUSE)
        query = urllib.parse.urlencode({'reporterCode': reporter_code, 'period': year, 'cmdCode': hs, 'flowCode': 'M'})
        body = fetch_json(f'{API}?{query}')
        rows = [r for r in (body or {}).get('data', []) if r.get('partner2Code') == 0 and r.get('motCode') == 0 and r.get('customsCode') == 'C00']
        total = next((r['primaryValue'] for r in rows if r['partnerCode'] == 0), None)
        if not total:
            continue
        named = {}
        for r in rows:
            iso = partners.get(r['partnerCode'])
            if iso and r['partnerCode'] != 0 and r['primaryValue'] > 0:
                named[iso] = named.get(iso, 0.0) + r['primaryValue']
        top = dict(sorted(named.items(), key=lambda kv: -kv[1])[:TOP_PARTNERS])
        # Shares, not the raw values: a derived market share is "transformed" data under the UN Comtrade re-dissemination policy.
        return {'year': year, 'total': round(total), 'shares': {k: round(100.0 * v / total, 1) for k, v in top.items()}}
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='only the first N reporters (for a trial run)')
    parser.add_argument('--resume', default=str(OUT) + '.partial')
    args = parser.parse_args()
    reporters, partners = reference()
    codes = sorted(reporters)[:args.limit] if args.limit else sorted(reporters)
    resume = Path(args.resume)
    done = json.loads(resume.read_text(encoding='utf-8')) if resume.exists() else {}
    jobs = [(c, key) for c in codes for key in COMMODITIES if f'{c}:{key}' not in done]
    print(f'{len(codes)} reporters, {len(jobs)} calls to make ({len(done)} already done)')

    def work(job):
        code, key = job
        while True:
            try:
                result = one(code, COMMODITIES[key][1], partners)
                break
            except QuotaExceeded as q:
                with _lock:
                    resume.write_text(json.dumps(done), encoding='utf-8')
                print(f'  quota used up; waiting {q.wait // 60} minutes ({len(done)} done so far)', flush=True)
                time.sleep(q.wait + 30)
        with _lock:
            done[f'{code}:{key}'] = result
            if len(done) % 25 == 0:
                resume.write_text(json.dumps(done), encoding='utf-8')
                print(f'  {len(done)} done', flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, jobs))
    resume.write_text(json.dumps(done), encoding='utf-8')

    imports = {}
    for code in codes:
        for key in COMMODITIES:
            entry = done.get(f'{code}:{key}')
            if entry:
                imports.setdefault(reporters[code], {})[key] = entry
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        'source': 'UN Comtrade public preview API (comtradeapi.un.org), goods imports by partner, annual',
        'license': ('UN Comtrade (UN Statistics Division). Shares computed from the data are transformed data, and a limited amount '
                    '(here under 100,000 records) may be used commercially under its re-dissemination policy; cite UN Comtrade on screen.'),
        'commodities': {k: {'label': v[0], 'hs': v[1]} for k, v in COMMODITIES.items()},
        'imports': imports,
    }, ensure_ascii=False, separators=(',', ':'), sort_keys=True), encoding='utf-8')
    print(f'wrote {OUT}: {len(imports)} countries')


if __name__ == '__main__':
    main()
