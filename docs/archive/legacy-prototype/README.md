# Legacy prototype

Unreferenced early-stage pages, kept for history — nothing in the live app
(`index.html`, `app.js`, `app.css`) loads or links to any of these:

- **globe-app.html** — an earlier "Event Globe" dashboard with its own
  inline sample data, superseded by `index.html`. Self-contained aside
  from `topojson.min.js`/`countries-110m.json`, which still live at the
  repo root and are shared with the live app.
- **globe.js** / **style.css** — a separate, also-unreferenced globe
  implementation from around the same period.
- **test.html** — a one-off check of whether the Three.js CDN build
  loads. The live globe is hand-rolled Canvas 2D, not Three.js.
- **test_api.html** — a manual browser-side smoke test of the backend
  API (health check + fetch crises). Superseded by
  `backend/scripts/check_data_sources.py` and the `backend/tests/`
  pytest suite, but still works standalone if you want to eyeball a
  live API response — points `frontend-api.js` back at the repo root.

All four HTML/JS files here had the same unescaped-`innerHTML` pattern
the live app was audited for (crisis/event title, country, etc.
interpolated into HTML without escaping) — fixed here too for
consistency, even though none of these pages are reachable from the app.
