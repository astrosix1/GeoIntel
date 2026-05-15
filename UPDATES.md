# GeoIntel — Development Updates (May 14, 2026)

## 1. Globe Pin Visibility — Root Cause Fixed

**Problem:** Crisis pins were disappearing during globe rotation and too few were visible at any time.

**Root cause (three-part bug):**

| # | Bug | Fix |
|---|-----|-----|
| 1 | Ascending z-sort + `.slice(0, N)` selected the **back-facing** pins (lowest z) | Changed to `.slice(-N)` — takes the **last** N after ascending sort = highest z = most front-facing |
| 2 | z-depth filter removed → back-facing pins rendered through the sphere | Restored `.filter(({p}) => p.z > 0)` to correctly hide pins behind the globe |
| 3 | Zoom multiplier formula `zoom/2` halved the display limit at normal zoom | Changed to `zoom` — so at zoom=1.0 the full `crisisDisplayLimit` is used |

**Final `drawPins` algorithm:**
```javascript
let visible = pool
  .map(c => ({ c, lat, lon, p: project(lat, lon), city }))
  .filter(({p}) => p.z > 0)           // hide pins behind the sphere
  .sort((a, b) => a.p.z - b.p.z)      // ascending z: edge → centre (painter's order)
  .slice(-maxDisplayLimit);            // LAST N = highest z = most centred/visible pins
```

---

## 2. Zoom-in Shows More Pins

**Problem:** Zooming in didn't reveal additional pins because only ~33 crises were ever front-facing at any rotation (limited candidate pool).

**Fixes:**
- Lowered location confidence threshold: `>= 75` → `>= 60` (24 more crises pass the filter)
- Added **120 new crises** with sub-regional specificity to the database

**Pin display counts by zoom level:**

| Zoom | Pins displayed |
|------|---------------|
| 0.4× (zoomed out) | ~36 |
| 1.0× (default) | 90 |
| 2.0× (zoomed in) | 180 |
| 3.0×+ | 250 (cap) |

---

## 3. Database Expansion — 104 → 224 Crises

Added 120 new crisis events across **110 countries** with geographically distinct coordinates so zooming into any region reveals sub-regional detail:

| Region | New crises added | Example sub-locations |
|--------|------------------|-----------------------|
| Europe | 21 | Ukraine (6 fronts), Baltic states, Balkans |
| Middle East | 15 | Gaza North/South, West Bank (×2), Lebanon, Syria (×2), Iraq (×2) |
| Africa | 28 | Sudan (×3), Ethiopia (×2), Somalia (×2), Nigeria (×3), DRC (×2), Sahel (×4) |
| Asia-Pacific | 25 | Taiwan Strait (×2), Korea (×2), India (×3), Myanmar (×3), Pakistan (×2) |
| Central Asia | 5 | Kyrgyz-Tajik border, Caucasus, Azerbaijan |
| Americas | 21 | Mexico (×4 cartels), Colombia (×2), Venezuela (×2), Haiti (×2), Brazil (×2) |
| Maritime | 5 | Strait of Hormuz, Red Sea, Arctic, Indian Ocean, Pacific Islands |

---

## 4. Cascade Simulation — Fully Implemented

**Backend (`GET /api/crises/<id>/cascade`):**
- Breadth-first search through the actor relationship graph
- Propagates crisis severity through alliances, conflicts, economic ties, and proxy relationships
- Each hop returns affected actors, escalation probability, mechanism description, and severity delta

**Frontend (⚡ Simulate Escalation button):**
- Calls the cascade API when a crisis is selected and the button is clicked
- Displays each escalation hop with probability percentage, mechanism, and severity increase
- Shows a summary header: total steps · overall probability · estimated timeline

---

## 5. All Files Changed

| File | Change |
|------|--------|
| `index.html` | Fixed `drawPins()` — sort direction, slice direction, z-filter restored |
| `index.html` | Zoom formula `zoom/2` → `zoom`; `crisisDisplayLimit` raised to 90 |
| `index.html` | Location confidence threshold lowered from 75 → 60 |
| `index.html` | ⚡ Cascade button wired to backend API with step-by-step result display |
| `backend/app.py` | Added `analyze_cascade()` BFS algorithm |
| `backend/app.py` | Added `GET /api/crises/<id>/cascade` endpoint |
| `backend/add_more_crises.py` | New script — inserted 120 crises (DB: 104 → 224 across 110 countries) |
