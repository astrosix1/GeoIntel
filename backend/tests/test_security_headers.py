"""Content-Security-Policy must allow every host the frontend fetches from
client-side — a missing one fails silently in the browser (see the country-
click incident noted in app.py)."""
import pytest


@pytest.mark.parametrize('host', [
    'https://tiles.openfreemap.org',   # base map vector tiles, style, glyphs
    'https://cdn.jsdelivr.net',        # country-boundary GeoJSON
    'https://tiles.maps.eox.at',       # premium Satellite layer (Sentinel-2)
    'https://s3.amazonaws.com',        # premium Topography layer (AWS elevation tiles)
    'https://api.rainviewer.com',      # Weather radar frame index
    'https://tilecache.rainviewer.com',  # Weather radar tiles
])
def test_csp_connect_src_allows_frontend_hosts(app_module, client, host):
    csp = client.get('/api/health').headers['Content-Security-Policy']
    connect_src = next(part for part in csp.split(';') if part.strip().startswith('connect-src'))
    assert host in connect_src
