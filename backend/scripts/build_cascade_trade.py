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
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://comtradeapi.un.org/public/v1/preview/C/A/HS'
REFERENCE = 'https://comtradeapi.un.org/files/v1/app/reference/'
YEARS = (2022, 2023, 2021)
TOP_PARTNERS = 12
BATCH = 8              # reporters per call: a call returns up to 500 rows and a country-commodity is about 40, so this stays under the cap
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


def entry_from(rows, partners, year):
    """{'year', 'total', 'shares': {iso: percent of the total}} from one reporter's rows, or None when there is no total."""
    rows = [r for r in rows if r.get('partner2Code') == 0 and r.get('motCode') == 0 and r.get('customsCode') == 'C00']
    total = next((r['primaryValue'] for r in rows if r['partnerCode'] == 0), None)
    if not total:
        return None
    named = {}
    for r in rows:
        iso = partners.get(r['partnerCode'])
        if iso and r['partnerCode'] != 0 and r['primaryValue'] > 0:
            named[iso] = named.get(iso, 0.0) + r['primaryValue']
    top = dict(sorted(named.items(), key=lambda kv: -kv[1])[:TOP_PARTNERS])
    # Shares, not the raw values: a derived market share is "transformed" data under the UN Comtrade re-dissemination policy.
    return {'year': year, 'total': round(total), 'shares': {k: round(100.0 * v / total, 1) for k, v in top.items()}}


def fetch_batch(codes, hs, year):
    """The rows for several reporters in ONE call (the quota counts calls, not rows). Returns (rows by reporter code, truncated), where
    truncated means the preview's 500-row cap was hit and the batch must be split."""
    time.sleep(PAUSE)
    query = urllib.parse.urlencode({'reporterCode': ','.join(str(c) for c in codes), 'period': year, 'cmdCode': hs, 'flowCode': 'M'})
    body = fetch_json(f'{API}?{query}') or {}
    rows = body.get('data') or []
    by = {}
    for r in rows:
        by.setdefault(r['reporterCode'], []).append(r)
    return by, len(rows) >= 500


def resolve(codes, hs, partners, size):
    """{reporter code: entry or None} for these reporters: batched calls for the newest year, then the older years for those still empty."""
    out = {}
    remaining = list(codes)
    for year in YEARS:
        for i in range(0, len(remaining), size):
            chunk = remaining[i:i + size]
            by, truncated = fetch_batch(chunk, hs, year)
            if truncated and len(chunk) > 1:
                out.update(resolve(chunk, hs, partners, max(1, len(chunk) // 2)) if year == YEARS[0] else {})
                continue
            for code in chunk:
                entry = entry_from(by.get(code, []), partners, year)
                if entry:
                    out[code] = entry
        remaining = [c for c in remaining if c not in out]
        if not remaining:
            break
    for code in remaining:
        out[code] = None
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='only the first N reporters (for a trial run)')
    parser.add_argument('--resume', default=str(OUT) + '.partial')
    parser.add_argument('--batch', type=int, default=BATCH, help='reporters per call')
    args = parser.parse_args()
    reporters, partners = reference()
    codes = sorted(reporters)[:args.limit] if args.limit else sorted(reporters)
    resume = Path(args.resume)
    done = json.loads(resume.read_text(encoding='utf-8')) if resume.exists() else {}
    print(f'{len(codes)} reporters, {len(COMMODITIES)} commodity groups, {len(done)} entries already done', flush=True)

    for key, (label, hs) in COMMODITIES.items():
        pending = [c for c in codes if f'{c}:{key}' not in done]
        for i in range(0, len(pending), args.batch):
            chunk = pending[i:i + args.batch]
            while True:
                try:
                    result = resolve(chunk, hs, partners, args.batch)
                    break
                except QuotaExceeded as q:
                    resume.write_text(json.dumps(done), encoding='utf-8')
                    print(f'  quota used up; waiting {q.wait // 60} minutes ({len(done)} entries so far)', flush=True)
                    time.sleep(q.wait + 30)
            for code, entry in result.items():
                done[f'{code}:{key}'] = entry
            resume.write_text(json.dumps(done), encoding='utf-8')
            print(f'  {label}: {min(i + args.batch, len(pending))}/{len(pending)} reporters ({len(done)} entries)', flush=True)
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
