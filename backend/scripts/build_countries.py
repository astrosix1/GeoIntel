#!/usr/bin/env python3
"""
Dev-time generator for config/countries.json and config/geo/countries-50m.json.

The pipeline's location stage needs one canonical record per country: a
display name, every alias sources use for it (NewsAPI/ACLED names, GDELT's
FIPS-style names like "Korea, South" or "Burma", ISO codes, demonyms), the
ISO 3166-1 numeric code the frontend's world-atlas topojson uses as its
feature id, and a centroid for country-level pins. This script builds that
table from the vendored topojson plus pycountry (a dev-only dependency — the
output is committed JSON, so production needs neither):

    pip install pycountry
    cd backend && python scripts/build_countries.py

Re-run it only when the topojson or the curated tables below change.
"""
import json
import math
import os
import shutil

import pycountry

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(BACKEND_DIR)
SRC_TOPO = os.path.join(REPO_DIR, 'countries-50m.json')
DST_TOPO = os.path.join(BACKEND_DIR, 'config', 'geo', 'countries-50m.json')
DST_TABLE = os.path.join(BACKEND_DIR, 'config', 'countries.json')

# Topojson features with no ISO numeric id get stable pseudo-codes.
PSEUDO_CODES = {'Kosovo': 'XKX', 'Somaliland': 'SOL', 'N. Cyprus': 'CYN'}
SKIP_FEATURES = {'Indian Ocean Ter.', 'Siachen Glacier'}

# Display names: the Actor roster's spelling where one exists (analyze_cascade
# matches Crisis.country to Actor.name), otherwise the everyday name.
DISPLAY_NAMES = {
    '840': 'United States', '826': 'United Kingdom', '643': 'Russia', '156': 'China', '364': 'Iran',
    '760': 'Syria', '410': 'South Korea', '408': 'North Korea', '180': 'DR Congo', '178': 'Republic of the Congo',
    '704': 'Vietnam', '158': 'Taiwan', '068': 'Bolivia', '862': 'Venezuela', '834': 'Tanzania',
    '498': 'Moldova', '418': 'Laos', '275': 'Palestine', '792': 'Turkey', '203': 'Czech Republic',
    '384': 'Ivory Coast', '583': 'Micronesia', '096': 'Brunei', '336': 'Vatican City', '132': 'Cape Verde',
    '748': 'Eswatini', '807': 'North Macedonia', '626': 'Timor-Leste', '104': 'Myanmar',
    '070': 'Bosnia and Herzegovina', '784': 'United Arab Emirates', '728': 'South Sudan',
    '140': 'Central African Republic', '732': 'Western Sahara', 'XKX': 'Kosovo', 'SOL': 'Somaliland',
    'CYN': 'Northern Cyprus',
}

# Extra aliases: GDELT FIPS-style names, common short forms, constituent parts.
EXTRA_ALIASES = {
    '840': ['US', 'USA', 'U.S.', 'U.S.A.', 'America', 'United States of America'],
    '826': ['UK', 'U.K.', 'Britain', 'Great Britain', 'England', 'Scotland', 'Wales', 'Northern Ireland'],
    '180': ['DRC', 'Congo, Democratic Republic of the', 'Democratic Republic of the Congo',
            'Democratic Republic of Congo', 'Congo-Kinshasa', 'Zaire', 'Dem. Rep. Congo'],
    '178': ['Congo', 'Congo, Republic of the', 'Congo-Brazzaville', 'Republic of Congo'],
    '410': ['Korea, South', 'Republic of Korea', 'ROK'],
    '408': ['Korea, North', 'DPRK', "Democratic People's Republic of Korea"],
    '104': ['Burma'],
    '384': ["Cote d'Ivoire", "Côte d'Ivoire"],
    '275': ['Gaza Strip', 'West Bank', 'Gaza', 'Palestinian Territories', 'Occupied Palestinian Territory',
            'Palestinian Territory', 'State of Palestine'],
    '807': ['Macedonia'],
    '748': ['Swaziland'],
    '626': ['East Timor'],
    '044': ['Bahamas, The'],
    '270': ['Gambia, The'],
    '784': ['UAE', 'Emirates'],
    '682': ['KSA'],
    '070': ['Bosnia', 'Bosnia-Herzegovina'],
    '643': ['Russian Federation'],
    '792': ['Türkiye', 'Turkiye'],
    '203': ['Czechia'],
    '336': ['Holy See', 'Vatican'],
    '158': ['Republic of China'],
    '156': ["People's Republic of China", 'PRC'],
    '364': ['Islamic Republic of Iran'],
    '728': ['S. Sudan'],
    '140': ['Central African Rep.', 'CAR'],
    'XKX': ['Kosova'],
    'CYN': ['N. Cyprus', 'Turkish Republic of Northern Cyprus'],
}

# CAMEO / legacy three-letter codes that differ from ISO 3166-1 alpha-3.
ISO3_ALIASES = {'642': ['ROM'], '180': ['ZAR'], '626': ['TMP'], '688': ['SCG'], 'XKX': ['KSV']}

DEMONYMS = {
    '840': ['American'], '156': ['Chinese'], '643': ['Russian'], '804': ['Ukrainian'], '364': ['Iranian'],
    '376': ['Israeli'], '275': ['Palestinian'], '422': ['Lebanese'], '760': ['Syrian'], '368': ['Iraqi'],
    '887': ['Yemeni'], '682': ['Saudi'], '784': ['Emirati'], '634': ['Qatari'], '792': ['Turkish'],
    '818': ['Egyptian'], '434': ['Libyan'], '729': ['Sudanese'], '728': ['South Sudanese'],
    '231': ['Ethiopian'], '232': ['Eritrean'], '706': ['Somali'], '404': ['Kenyan'], '566': ['Nigerian'],
    '466': ['Malian'], '854': ['Burkinabe'], '562': ['Nigerien'], '148': ['Chadian'], '180': ['Congolese'],
    '646': ['Rwandan'], '800': ['Ugandan'], '710': ['South African'], '012': ['Algerian'],
    '504': ['Moroccan'], '788': ['Tunisian'], '004': ['Afghan'], '586': ['Pakistani'], '356': ['Indian'],
    '050': ['Bangladeshi'], '104': ['Burmese'], '764': ['Thai'], '704': ['Vietnamese'], '608': ['Filipino'],
    '360': ['Indonesian'], '458': ['Malaysian'], '158': ['Taiwanese'], '392': ['Japanese'],
    '410': ['South Korean'], '408': ['North Korean'], '496': ['Mongolian'], '398': ['Kazakh'],
    '860': ['Uzbek'], '268': ['Georgian'], '051': ['Armenian'], '031': ['Azerbaijani'],
    '112': ['Belarusian'], '616': ['Polish'], '440': ['Lithuanian'], '428': ['Latvian'], '233': ['Estonian'],
    '246': ['Finnish'], '752': ['Swedish'], '578': ['Norwegian'], '208': ['Danish'], '276': ['German'],
    '250': ['French'], '826': ['British'], '380': ['Italian'], '724': ['Spanish'], '300': ['Greek'],
    '688': ['Serbian'], 'XKX': ['Kosovar'], '070': ['Bosnian'], '348': ['Hungarian'], '642': ['Romanian'],
    '498': ['Moldovan'], '484': ['Mexican'], '170': ['Colombian'], '862': ['Venezuelan'], '192': ['Cuban'],
    '332': ['Haitian'], '076': ['Brazilian'], '032': ['Argentine', 'Argentinian'], '604': ['Peruvian'],
    '218': ['Ecuadorian'], '068': ['Bolivian'], '152': ['Chilean'], '124': ['Canadian'],
    '036': ['Australian'], '554': ['New Zealand'], '288': ['Ghanaian'], '686': ['Senegalese'],
    '120': ['Cameroonian'], '508': ['Mozambican'], '716': ['Zimbabwean'], '140': ['Central African'],
}


def decode_arcs(topo):
    sx, sy = topo['transform']['scale']
    tx, ty = topo['transform']['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)
    return arcs


def ring_points(ring, arcs):
    points = []
    for index in ring:
        arc = arcs[index] if index >= 0 else list(reversed(arcs[~index]))
        points.extend(arc if not points else arc[1:])
    return points


def polygons_of(geometry, arcs):
    if geometry['type'] == 'Polygon':
        return [[ring_points(r, arcs) for r in geometry['arcs']]]
    if geometry['type'] == 'MultiPolygon':
        return [[ring_points(r, arcs) for r in poly] for poly in geometry['arcs']]
    return []


def unwrap_ring(points):
    """Make longitudes continuous across the antimeridian (a jump of more
    than 180 degrees between neighbours is really a wrap)."""
    out = []
    offset = 0.0
    prev = None
    for x, y in points:
        if prev is not None:
            if x + offset - prev > 180:
                offset -= 360
            elif x + offset - prev < -180:
                offset += 360
        out.append((x + offset, y))
        prev = x + offset
    return out


def wrap_lon(lon):
    return (lon + 180) % 360 - 180


def ring_area_centroid(points):
    points = unwrap_ring(points)
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area /= 2
    if abs(area) < 1e-12:
        xs, ys = zip(*points)
        return 0.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    return abs(area), (cx / (6 * area), cy / (6 * area))


def main():
    os.makedirs(os.path.dirname(DST_TOPO), exist_ok=True)
    shutil.copyfile(SRC_TOPO, DST_TOPO)
    with open(SRC_TOPO, 'r', encoding='utf-8') as f:
        topo = json.load(f)
    arcs = decode_arcs(topo)

    countries = []
    for geometry in topo['objects']['countries']['geometries']:
        topo_name = geometry['properties']['name']
        if topo_name in SKIP_FEATURES:
            continue
        code = geometry.get('id') or PSEUDO_CODES.get(topo_name)
        if not code:
            continue
        iso = pycountry.countries.get(numeric=code) if code.isdigit() else None

        # Centroid of the largest polygon's outer ring (so France's pin is in
        # France, not averaged with French Guiana).
        largest = max(
            (ring_area_centroid(poly[0]) for poly in polygons_of(geometry, arcs) if poly and poly[0]),
            default=(0, (0.0, 0.0)),
        )
        lon, lat = largest[1]
        lon = wrap_lon(lon)

        name = DISPLAY_NAMES.get(code) or (getattr(iso, 'common_name', None) if iso else None) \
            or (iso.name if iso else topo_name)
        aliases = {name, topo_name}
        if iso:
            aliases.update(filter(None, [iso.name, getattr(iso, 'official_name', None),
                                         getattr(iso, 'common_name', None)]))
        aliases.update(EXTRA_ALIASES.get(code, []))
        aliases.discard('')
        countries.append({
            'code': code,
            'name': name,
            'iso2': iso.alpha_2 if iso else None,
            'iso3': iso.alpha_3 if iso else code,
            'iso3_aliases': ISO3_ALIASES.get(code, []),
            'aliases': sorted(a for a in aliases if a != name),
            'demonyms': DEMONYMS.get(code, []),
            'centroid': [round(lat, 4), round(lon, 4)],
        })

    countries.sort(key=lambda c: c['name'])
    with open(DST_TABLE, 'w', encoding='utf-8') as f:
        json.dump({
            '_comment': 'Generated by scripts/build_countries.py — edit the tables in that script, not this '
                        'file. code = ISO 3166-1 numeric (the world-atlas topojson feature id the frontend '
                        'uses); pseudo-codes XKX/SOL/CYN for features without one. centroid = [lat, lon] of '
                        'the largest landmass.',
            'countries': countries,
        }, f, ensure_ascii=False, indent=1)
    print(f"Wrote {len(countries)} countries to {DST_TABLE}")


if __name__ == '__main__':
    main()
