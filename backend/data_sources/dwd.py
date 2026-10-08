"""
Deutscher Wetterdienst (DWD) global ICON forecast layers, served as a keyless WMS (maps.dwd.de). The browser draws the map tiles
itself; this module only reads the service's capabilities once in a while to learn which forecast times each layer has, so the
app never offers a time the service cannot draw.

Licence (checked 2026-10-08 against DWD's legal notice, dwd.de "Rechtliche Hinweise"): freely accessible geodata and geodata
services, which include all weather and climate information with a place reference, may be reused under CC BY 4.0 with a source
line. Source line used on screen: "Quelle: Deutscher Wetterdienst".
"""
import logging
import re
from datetime import datetime, timedelta, timezone

try:
    import requests
except Exception:
    requests = None

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

WMS = 'https://maps.dwd.de/geoserver/dwd/wms'
CAPABILITIES = f'{WMS}?service=WMS&version=1.3.0&request=GetCapabilities'
CACHE_SECONDS = 30 * 60
MAX_TIMES = 260
ATTRIBUTION = {'text': 'Quelle: Deutscher Wetterdienst (ICON)', 'url': 'https://www.dwd.de/', 'license': 'CC BY 4.0',
               'license_url': 'https://creativecommons.org/licenses/by/4.0/'}

# our layer key -> (WMS layer name, label)
LAYERS = {
    'temperature': ('Icon_reg025_fd_sl_T2M', 'Air temperature (2 m)'),
    'pressure': ('Icon_reg025_fd_sl_PMSL', 'Sea-level pressure'),
    'rain': ('Icon_reg025_fd_sl_TOTPREC06H', 'Rain in the 6 hours before'),
    'wind': ('Icon_reg025_fd_sl_UV10M', 'Wind speed (10 m)'),
}


def _parse_iso(text):
    return datetime.fromisoformat(text.strip().replace('Z', '+00:00')).astimezone(timezone.utc)


def parse_times(value):
    """The ISO times of a WMS time dimension, which is either 'start/end/PT3H' (one or more ranges, comma separated) or a plain
    comma list. Returns [] for anything unreadable."""
    out = []
    for part in (value or '').split(','):
        part = part.strip()
        if not part:
            continue
        pieces = part.split('/')
        try:
            if len(pieces) == 3:
                start, end = _parse_iso(pieces[0]), _parse_iso(pieces[1])
                match = re.fullmatch(r'PT(\d+)H', pieces[2].strip())
                step = timedelta(hours=int(match.group(1))) if match else None
                if not step:
                    continue
                t = start
                while t <= end and len(out) < MAX_TIMES * 2:
                    out.append(t)
                    t += step
            else:
                out.append(_parse_iso(pieces[0]))
        except (ValueError, TypeError):
            continue
    out = sorted(set(out))
    return [t.strftime('%Y-%m-%dT%H:%M:%SZ') for t in out[-MAX_TIMES:]]


def _layer_times(xml, wms_name):
    i = xml.find(f'<Name>{wms_name}</Name>')
    if i < 0:
        return []
    j = xml.find('</Layer>', i)
    match = re.search(r'<Dimension[^>]*name="time"[^>]*>([^<]*)</Dimension>', xml[i:j])
    return parse_times(match.group(1)) if match else []


def layers():
    """{'layers': {key: {'wms_layer', 'label', 'times': [ISO...]}}, 'attribution', 'fetched_at'} or None when DWD cannot be reached.
    A layer whose times cannot be read is left out, so the app never offers it."""
    cached = cache_get('dwd:layers')
    if cached is not None:
        return cached or None
    if not requests:
        return None
    try:
        resp = requests.get(CAPABILITIES, timeout=25, headers={'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)'})
        resp.raise_for_status()
        xml = resp.text
    except Exception as e:
        logger.warning('[DWD] capabilities failed: %s', e)
        return None
    found = {}
    for key, (name, label) in LAYERS.items():
        times = _layer_times(xml, name)
        if times:
            found[key] = {'wms_layer': name, 'label': label, 'times': times}
    if not found:
        return None
    result = {'layers': found, 'attribution': ATTRIBUTION, 'fetched_at': datetime.now(timezone.utc).isoformat()}
    cache_set('dwd:layers', result, ttl=CACHE_SECONDS)
    return result
