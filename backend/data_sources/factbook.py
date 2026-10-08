"""
CIA World Factbook connector: real, free, no key, public domain.

Reads the per-country JSON files of the factbook.json mirror (github.com/factbook/factbook.json). Each file sits in a
region folder and is named by the Factbook's own (FIPS-style) country code, so factbook_codes.json maps ISO alpha-2 to
(folder, code). Every parser returns None for anything it cannot read cleanly, so the caller shows "unavailable"
instead of a guess; free text it cannot split is kept as the Factbook's own words.
"""
import html
import json
import logging
import re
from pathlib import Path

try:
    import requests
except Exception:
    requests = None

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

FACTBOOK_BASE = 'https://raw.githubusercontent.com/factbook/factbook.json/master'
CACHE_SECONDS = 24 * 3600

_CODES = None


def _codes():
    global _CODES
    if _CODES is None:
        _CODES = json.loads((Path(__file__).parent / 'factbook_codes.json').read_text(encoding='utf-8'))
    return _CODES


def clean(value):
    """Plain text from a Factbook field: unwrap {'text': ...}, drop tags and entities, squeeze spaces."""
    if isinstance(value, dict):
        value = value.get('text')
    if not isinstance(value, str):
        return None
    text = re.sub(r'<[^>]+>', ' ', value)
    text = html.unescape(text).replace('�', '').replace('\xa0', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text or None


def _field(data, section, key):
    return clean(((data.get(section) or {}).get(key)))


def _as_of(text):
    match = re.search(r'\((?:FY)?(\d{4})(?: est\.)?\)', text or '')
    return int(match.group(1)) if match else None


def parse_shares(text):
    """'Roman Catholic 47%, Muslim 4%, none 33% (2021 est.)' -> {'items': [{'name','percent'}], 'as_of', 'note'}.
    Returns None when no name-and-percent pair can be read."""
    if not text:
        return None
    body, _, note = text.partition(' note:')
    as_of = _as_of(body)
    items = _read_shares(body)
    if not items:
        return None
    return {'items': items, 'as_of': as_of, 'note': note.strip() or None}


def _read_shares(body, depth=0):
    """Top-level 'name N%' pairs of a text. A bracket right after a pair ('Muslim 87% (includes Sunni 74%, Shia 13%)')
    is that item's sub-split and is read the same way into 'children'; other brackets (dates, remarks) are dropped."""
    groups, top, level, start = [], '', 0, 0
    for i, char in enumerate(body):
        if char == '(':
            if level == 0:
                start = i + 1
            level += 1
        elif char == ')' and level > 0:
            level -= 1
            if level == 0:
                groups.append(body[start:i])
                top += '\x00%d\x00' % (len(groups) - 1)
        elif level == 0:
            top += char
    items = []
    pattern = r'(?:^|[,;])\s*([^,;%\x00]*?[A-Za-z][^,;%\x00]*?)\s+(?:\x00\d+\x00\s+)?(<\s*|~\s*)?(\d+(?:\.\d+)?)\s*%\s*(?:\x00(\d+)\x00)?'
    for match in re.finditer(pattern, top):
        name = match.group(1).strip(' :')
        if depth:
            name = re.sub(r'^(?:(?:includes|including|of which|to include|and)\s+)+', '', name, flags=re.I)
        if not name:
            continue
        item = {'name': name, 'percent': float(match.group(3)), 'under': (match.group(2) or '').startswith('<')}
        if match.group(4) is not None and depth < 2:
            inner = re.sub(r'^\s*(?:includes|including|of which|to include)\s*:?\s*', '', groups[int(match.group(4))])
            children = _read_shares(inner, depth + 1)
            if children:
                item['children'] = children
        items.append(item)
    return items


def parse_age_structure(raw):
    """Factbook age structure -> [{'band','percent','male','female','count'}] for the bands it lists."""
    if not isinstance(raw, dict):
        return None
    bands = []
    for band, value in raw.items():
        text = clean(value)
        if not text or band == 'note' or not re.match(r'\d', band):
            continue
        pct = re.match(r'(\d+(?:\.\d+)?)%', text)
        counts = re.search(r'male ([\d,]+)/female ([\d,]+)', text)
        if not pct:
            continue
        male = int(counts.group(1).replace(',', '')) if counts else None
        female = int(counts.group(2).replace(',', '')) if counts else None
        bands.append({
            'band': band, 'percent': float(pct.group(1)), 'male': male, 'female': female,
            'count': male + female if male is not None and female is not None else None,
            'as_of': _as_of(text),
        })
    return bands or None


def parse_rate(text):
    """'10.88 births/1,000 population (2025 est.)' -> {'value': 10.88, 'as_of': 2025}."""
    if not text:
        return None
    match = re.match(r'(-?\d+(?:,\d{3})*(?:\.\d+)?)', text)
    return {'value': float(match.group(1).replace(',', '')), 'as_of': _as_of(text)} if match else None


def parse_list(text):
    """'aircraft, cars, packaged medicine (2023)' -> (['aircraft', ...], 2023). Lists are split on commas outside brackets."""
    if not text:
        return None
    as_of = _as_of(text)
    body = re.sub(r'\s*\((?:FY)?\d{4}(?: est\.)?\)\s*', ' ', text)
    body = body.partition(' note:')[0]
    parts, depth, current = [], 0, ''
    for char in body:
        depth += (char == '(') - (char == ')')
        if char in ',;' and depth <= 0:
            parts.append(current)
            current = ''
        else:
            current += char
    parts.append(current)
    items = [p.strip(' .') for p in parts if p.strip(' .')]
    return {'items': items, 'as_of': as_of} if items else None


def parse_partners(text):
    """'United States 14%, Germany 9% (2023)' -> shares; same reader as religions."""
    return parse_shares(text)


def _subfield(data, section, key, sub):
    node = (data.get(section) or {}).get(key)
    return clean(node.get(sub)) if isinstance(node, dict) else None


def _names(text):
    """Leaders: 'President Emmanuel MACRON (since 14 May 2017)' -> {'title','name','since'} best effort, else raw."""
    if not text:
        return None
    since = re.search(r'\(since ([^)]+)\)', text)
    base = re.sub(r'\s*\(since [^)]+\)', '', text).strip()
    return {'text': text, 'since': since.group(1) if since else None, 'summary': base}


def _languages_text(data):
    """The Factbook nests the language list one level down ({'Languages': {'Languages': {'text': ...}}}) for some countries."""
    node = (data.get('People and Society') or {}).get('Languages')
    if isinstance(node, dict) and isinstance(node.get('Languages'), (dict, str)):
        return clean(node['Languages'])
    return clean(node)


def parse_cities(text):
    """'11.208 million PARIS (capital), 1.761 million Lyon, 996,000 Hamah (2023)' ->
    {'items': [{'name', 'population', 'capital'}], 'as_of': 2023}. Names the Factbook writes in capitals are the capital."""
    if not text:
        return None
    as_of = _as_of(text)
    body = re.sub(r'\s*\((?:FY)?\d{4}(?: est\.)?\)\s*$', '', text)
    items = []
    for part in re.split(r',\s+(?=\d)', body):
        match = re.match(r'\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(million|thousand)?\s+(.+?)\s*$', part)
        if not match:
            continue
        number = float(match.group(1).replace(',', ''))
        number *= {'million': 1_000_000, 'thousand': 1_000}.get(match.group(2), 1)
        name = match.group(3)
        capital = '(capital)' in name
        name = re.sub(r'\s*\(capital\)', '', name).strip()
        if capital and name.isupper():
            name = name.title()
        if name:
            items.append({'name': name, 'population': round(number), 'capital': capital})
    return {'items': items, 'as_of': as_of} if items else None



def parse_profile(data):
    """The whole Factbook file -> only the fields the app shows. Missing pieces are simply absent."""
    if not isinstance(data, dict):
        return None
    gov = data.get('Government') or {}
    people = data.get('People and Society') or {}
    out = {
        'government': {
            'type': _field(data, 'Government', 'Government type'),
            'capital': _subfield(data, 'Government', 'Capital', 'name'),
            'chief_of_state': _names(_subfield(data, 'Government', 'Executive branch', 'chief of state')),
            'head_of_government': _names(_subfield(data, 'Government', 'Executive branch', 'head of government')),
            'cabinet': _subfield(data, 'Government', 'Executive branch', 'cabinet'),
            'election_process': _subfield(data, 'Government', 'Executive branch', 'election/appointment process'),
            'constitution': {
                'history': _subfield(data, 'Government', 'Constitution', 'history'),
                'amendment': _subfield(data, 'Government', 'Constitution', 'amendment process'),
            },
            'legislative': _subfield(data, 'Government', 'Legislative branch', 'description'),
            'judicial': _subfield(data, 'Government', 'Judicial branch', 'highest courts'),
            'parties': _field(data, 'Government', 'Political parties and leaders'),
            'legal_system': _field(data, 'Government', 'Legal system'),
            'suffrage': _field(data, 'Government', 'Suffrage'),
        },
        'people': {
            'religions': parse_shares(_field(data, 'People and Society', 'Religions')),
            'ethnic_groups': parse_shares(_field(data, 'People and Society', 'Ethnic groups')),
            'ethnic_groups_text': _field(data, 'People and Society', 'Ethnic groups'),
            'age_structure': parse_age_structure(people.get('Age structure')),
            'birth_rate': parse_rate(_field(data, 'People and Society', 'Birth rate')),
            'death_rate': parse_rate(_field(data, 'People and Society', 'Death rate')),
            'net_migration_rate': parse_rate(_field(data, 'People and Society', 'Net migration rate')),
            'median_age': _subfield(data, 'People and Society', 'Median age', 'total'),
            'languages': _languages_text(data),
            'language_shares': parse_shares(_languages_text(data)),
            'major_cities': parse_cities(_field(data, 'People and Society', 'Major urban areas - population')),
        },
        'economy': {
            'exports': parse_list(_field(data, 'Economy', 'Exports - commodities')),
            'imports': parse_list(_field(data, 'Economy', 'Imports - commodities')),
            'export_partners': parse_shares(_field(data, 'Economy', 'Exports - partners')),
            'import_partners': parse_shares(_field(data, 'Economy', 'Imports - partners')),
            'natural_resources': parse_list(_field(data, 'Geography', 'Natural resources')),
        },
        'infrastructure': {
            'airports': _subfield(data, 'Transportation', 'Airports', 'total') or _field(data, 'Transportation', 'Airports'),
            'ports': _subfield(data, 'Transportation', 'Ports', 'total ports'),
            'key_ports': _subfield(data, 'Transportation', 'Ports', 'key ports'),
            'railways': _subfield(data, 'Transportation', 'Railways', 'total'),
            'roadways': _subfield(data, 'Transportation', 'Roadways', 'total'),
            'electricity_access': _subfield(data, 'Energy', 'Electricity access', 'electrification - total population'),
        },
        'security': {
            'terrorist_groups': _field(data, 'Terrorism', 'Terrorist group(s)'),
            'refugees': _subfield(data, 'Transnational Issues', 'Refugees and internally displaced persons', 'refugees'),
            'idps': _subfield(data, 'Transnational Issues', 'Refugees and internally displaced persons', 'IDPs'),
            'military_branches': _field(data, 'Military and Security', 'Military and security forces'),
        },
    }
    return out


class FactbookConnector:
    @staticmethod
    def fetch_profile(iso2):
        """Parsed Factbook facts for an ISO alpha-2 code, or None if the country is unmapped or the fetch fails."""
        if not requests or not iso2:
            return None
        entry = _codes().get(iso2.upper())
        if not entry:
            return None
        key = f'factbook:{iso2.upper()}'
        cached = cache_get(key)
        if cached is not None:
            return cached
        region, code = entry
        try:
            resp = requests.get(f'{FACTBOOK_BASE}/{region}/{code}.json', timeout=10)
            if resp.status_code != 200:
                logger.info('[Factbook] %s -> HTTP %s', iso2, resp.status_code)
                return None
            profile = parse_profile(resp.json())
        except Exception as e:  # network or bad JSON: unavailable, never fabricated
            logger.info('[Factbook] %s failed: %s', iso2, e)
            return None
        if profile:
            cache_set(key, profile, ttl=CACHE_SECONDS)
        return profile
