"""
OEC (Observatory of Economic Complexity) connector — real top-export
commodity data, best-effort/unauthenticated.

Live-verified at implementation time (2026-09-29): the public
`https://api-v2.oec.world/tesseract/data.jsonrecords` endpoint is
reachable without any API key or registration and returns HTTP 200, but
querying it for a real country's export mix (e.g. France, cube
`trade_i_baci_a_92`, drilldown `HS4`, `Exporter Country=fra`) came back
with an empty result set (`"total": 0`, `"data": []`) even though the
endpoint itself is live and documents that exact dataset. That matches
the plan's caveat ("confirmed free unauthenticated access to profile
data, though heavier access needs a free tier") — the unauthenticated
tier answers but doesn't actually hand back usable commodity-level rows
for this app's real usage pattern.

Per the no-fabrication rule, this connector does NOT invent export
figures when OEC returns nothing usable. It returns None, and
services/country_profile.py falls back to WorldBank's real
trade-as-%-GDP figures (already integrated) for the trade section,
representing top-exports-by-commodity as honestly unavailable.
"""
import logging

try:
    import requests
except Exception:
    requests = None

logger = logging.getLogger(__name__)

OEC_BASE = "https://api-v2.oec.world/tesseract/data.jsonrecords"

# OEC's country drilldown expects lowercase 3-letter trade-partner codes
# (their own "id" scheme, e.g. "fra", "chn") - separate from ISO alpha-2.
# We only ship a small, explicit map for the codes this app is likely to
# query rather than guessing a transliteration for every country.
_ISO2_TO_OEC = {
    'FR': 'fra', 'US': 'usa', 'CN': 'chn', 'RU': 'rus', 'JP': 'jpn',
    'DE': 'deu', 'IN': 'ind', 'GB': 'gbr', 'BR': 'bra', 'UA': 'ukr',
    'IL': 'isr', 'IR': 'irn', 'KP': 'prk', 'KR': 'kor', 'SA': 'sau',
}


class OECConnector:
    """Best-effort fetch of a country's top exported product categories."""

    @staticmethod
    def fetch_top_exports(iso2_code, year=2022, limit=5):
        """
        Returns a list of {hs4, trade_value_usd} dicts on success, or None
        if OEC's unauthenticated tier doesn't return usable data (the live,
        verified behavior for at least one real country as of this
        implementation) — never a fabricated commodity list.
        """
        if not requests or not iso2_code:
            return None

        oec_code = _ISO2_TO_OEC.get(iso2_code.upper())
        if not oec_code:
            logger.info(f"[OEC] no known OEC country code mapping for {iso2_code}")
            return None

        try:
            resp = requests.get(
                OEC_BASE,
                params={
                    'cube': 'trade_i_baci_a_92',
                    'drilldowns': 'HS4',
                    'measures': 'Trade Value',
                    'Year': year,
                    'Exporter Country': oec_code,
                    'sort': 'Trade Value.desc',
                    'limit': limit,
                },
                timeout=6,
            )
            if resp.status_code != 200:
                logger.info(f"[OEC] {iso2_code} -> HTTP {resp.status_code}, unavailable")
                return None

            payload = resp.json()
            rows = payload.get('data') or []
            if not rows:
                logger.info(f"[OEC] {iso2_code} -> unauthenticated tier returned no usable rows (total={payload.get('page', {}).get('total')})")
                return None

            return [
                {
                    'hs4': row.get('HS4') or row.get('HS4 ID'),
                    'trade_value_usd': row.get('Trade Value'),
                }
                for row in rows
            ]
        except Exception as e:
            logger.info(f"[OEC] fetch failed for {iso2_code}: {e}")
            return None
