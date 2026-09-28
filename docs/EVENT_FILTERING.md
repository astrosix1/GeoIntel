# Event Filtering System: Locations, Relevance, Duplicates, Severity, Titles

## Context

The globe and sidebar are flooded with events that are misplaced, off-topic, duplicated, over-rated and badly titled. Investigation (code reading plus a live GDELT file run through the current parser in memory) traced every symptom to ingestion in `backend/data_sources.py`, with a few frontend amplifiers:

| Symptom | Root cause (verified) |
|---|---|
| Wrong-country pins | NewsAPI pins the earliest `LOCATION_MAP` city (`_find_earliest_city`, data_sources.py:1021). Ambiguous names (`washington`, `victoria`→Seychelles, `georgetown`→Guyana, `san jose`, `kingston`, `perth`, `santiago`, `cali`) and capital-as-government metonymy ("Washington sanctions Venezuela" → US pin) both go wrong. The AI geocoder (`_extract_incident_location`, :679) calls the retired `claude-3-5-sonnet-20241022`, so it has probably always failed silently. GDELT `ActionGeo` is inferred from any place named in an article: one politico.eu piece became 18 pins in Berlin, Miami and Florida. Frontend ring-spreads co-located pins up to 55px (app.js:1709-1737), which pushes them over borders. |
| Non-geopolitical events | Keyword matching is a plain substring check (:1165, :1240): `'ai'` matches "s**ai**d" (→ technology), `'war'` matches "soft**war**e/to**war**ds/**War**saw" (severity 80), and "heart attack" counts as an attack. GDELT has no actor, root-event or source filters: an F1 article became a "conflict in Baku", and a 1934 cruise-ship history piece became a FIGHT with severity 100. |
| Duplicates | GDELT emits many GlobalEventIDs per article: 186 events came from only 60 URLs in one 15-minute file. No cross-source or near-duplicate matching exists anywhere; the only match is on `Crisis.id`. The NewsAPI id `news_{source}_{date}` (:1245) *collides* across articles, and `newsapi_multilingual.py` inserts directly, bypassing upsert. Nothing ever sets `is_active=False`, so events pile up forever. |
| Too many high-severity | GDELT severity = `-Goldstein*10`, but Goldstein is a fixed constant per CAMEO code, so every "fight" scores 100. 31% of live GDELT events scored ≥80. News severity starts at 50 and substring hits add to it. ACLED uses `30 + fatalities//2`. The frontend alert badge counts all ≥80 events, ignoring filters (app.js:2805). |
| Bad titles | ACLED title = `event_id_cnty`, an ID code (:237). GDELT title = `"Unknown actor — conflict event in X"` (:1533). NewsAPI headlines keep suffixes like "- Reuters" or "\| BBC News", and live-blog headlines are often just dates. |

**Decisions:** severity becomes **two scores**, local `severity` and a new `global_impact`, with `global_impact` driving emphasis and the critical badge. **Rules only, no LLM**: remove the dead AI geocoding path. **GDELT stays a standalone source with a strict filter.**

**Outcome:** every candidate event passes through one deterministic, configurable, unit-tested pipeline that rejects, relocates, merges and scores events. Each decision gets a reason code, reported per sync.

---

## Architecture

New package `backend/event_pipeline/` of pure functions (no DB or network except where noted), run by `DataAggregator` between fetch and upsert. **All** sources route through it, including the multilingual sync, which today bypasses upsert.

```
fetch (ACLED / GDELT / NewsAPI / multilingual)
  → normalize.py   canonical fields, country normalization, URL canonicalization, stable ids
  → relevance.py   geopolitical gate + outlet/domain filter            (reject: reason code)
  → location.py    validate / correct / assign precision              (reject or relocate)
  → titles.py      clean or synthesize display title                  (reject if unfixable)
  → dedup.py       collapse within batch, then match vs active DB rows (merge into primary)
  → scoring.py     severity (local intensity) + global_impact
  → upsert         DataAggregator._upsert_crisis / _merge_into_primary
report.py: PipelineReport counts per source × stage × reason, plus severity/global_impact histograms
```

Files:
- `backend/event_pipeline/{__init__,normalize,relevance,location,titles,dedup,scoring,report,countries,geo}.py`
- `__init__.py` holds `process_batch(candidates, session) -> PipelineResult(kept, merged, rejected, report)`.
- `backend/config/event_filters.json` holds all tunables: keyword lists, outlet blocklist/tiers, GDELT code and actor rules, thresholds and weights. The code-free tuning style matches `source_reliability.json`.
- `backend/config/countries.json`: canonical country table with `name`, `aliases[]`, `iso2`, `iso3`, `iso_num` (the world-atlas topojson id), `fips` (for GDELT) and `demonyms[]`. Vendored JSON, so no new dependency.
- `backend/config/geo/countries-50m.json`: a vendored copy of the root file, because the backend Dockerfile only copies `backend/`.
- `backend/config/cameo_titles.json`: CAMEO 3-digit base code → verb phrase for GDELT title templates.

Each stage returns `Decision(keep: bool, reason: str, patch: dict)`. Candidates carry a transient `_meta` dict (raw GDELT fields, outlet, URL, fatalities, actor countries, precision) that is never persisted.

---

## 1. Locations (`location.py`, `countries.py`, `geo.py`)

**Shared checks (all sources)**
1. **Normalize the country** through the `countries.json` alias map ("UK"→"United Kingdom", "DRC"/"Congo, Democratic Republic"→"DR Congo", "Burma"→"Myanmar", "Gaza Strip"/"West Bank"/"Palestine"→"Palestine"). Set `country_code` (ISO numeric string, the same id the frontend topojson uses). Reject if the country can't be resolved (`reason=unknown_country`). This also fixes sample data putting "Kyiv" in `country`.
2. **Validate coordinates:** finite, within lat/lon range, not (0,0). **Point-in-country check**: `geo.point_in_country(lat, lon, iso_num, tolerance_km=25)`. It uses a pure-Python topojson arc decode, a per-country bbox prefilter and ray casting, loaded lazily and cached. The 25 km tolerance covers coastal and port points at 50m resolution. On a mismatch, look up which country actually contains the point. If that country is a party to the event (actor countries or a country named in the text), accept it and correct `country`. Otherwise reject with `coords_country_mismatch`.
3. **Set `location_precision`** to one of `point | city | region | country`. Country-precision events are kept but stored at the country centroid from `countries.json` and flagged, so the frontend renders them differently (see Frontend).

**GDELT**
- Precision comes from `ActionGeo_Type`: 3/4 → city, 2/5 → region, 1 → country.
- **Actor-location consistency:** convert Actor1/Actor2 CountryCode (CAMEO ≈ ISO3) through `countries.json`. If at least one actor has a country and the ActionGeo country matches *neither* actor country, fall back to Actor1Geo/Actor2Geo (cols 35-50; add their indexes) when one of those matches an actor country. Otherwise reject with `geo_actor_mismatch`. This rule kills the "Miami pin for a Berlin–Moscow meeting" case.
- Among collapsed events from the same URL (see Dedup), prefer the representative whose geo is consistent and most precise.

**NewsAPI (rules only)**
- Delete `_extract_incident_location` and `_geocode_ai_client`. Remove the NominatimGeocoder call from the news path (keep the class only if another caller exists; none does today, so delete it and `tests/test_geocoding.py`'s AI and Nominatim cases, rewriting the rest for the new resolver).
- New resolver `resolve_news_location(title, description)`:
  1. Strip the dateline (existing `DATELINE_RE`).
  2. **Metonymy guard:** a capital/city match immediately followed within 3 tokens by a government verb (`says|said|warns|urges|condemns|accuses|imposes|announces|rejects|denies|threatens|demands|calls|signals|responds|vows|blames|slams|sanctions`), or preceded by "officials in", is an *actor* reference, not a location. It is skipped for placement but counts as an actor signal.
  3. **Ambiguous names** (a list in config, `ambiguous_cities`) are accepted only if their country name or demonym also appears in the text, or no other location candidate exists *and* the country is an actor in the text.
  4. **Candidate scoring** instead of "earliest wins": title mention +3, description +1, preposition context (`in|near|outside|across|over|at`) +2, metonymy −5. City candidates come from `LOCATION_MAP`. Country candidates come from `countries.json` names and demonyms ("Sudanese army" → Sudan) at country precision. Highest score wins; on a tie, prefer the city whose country is also mentioned.
  5. If the only candidates are metonymic ("Washington warns Tehran" with no event place), place at the country of the *other* party (Iran), at country precision. If nothing survives, reject with `no_location`.
- Move `LOCATION_MAP` to `config/gazetteer.json` (also fixes the duplicate `islamabad` key and the 'US'/'UK' spellings via normalize).

**ACLED:** trust the coordinates (precise) but still run normalize and the polygon check. Precision is `point` when `geo_precision == 1`, `city` for 2, `region` for 3.

---

## 2. Events: geopolitical relevance + source filtering (`relevance.py`)

**All sources**
- Every keyword match uses compiled `\b...\b` regex (a shared `kw_regex(list)` helper). This fixes the `'ai'`/`'war'`/`'oil'`/`'gas'` substring bugs in both `CRISIS_KEYWORDS` and the severity keywords.
- **Outlet filter:** in `event_filters.json` → `outlets`:
  - `blocked_domains`: press-release wires (prnewswire, globenewswire, businesswire, accesswire), aggregators (biztoc), and sports/entertainment/motorsport sites (crash.net, espn, …).
  - `blocked_url_paths`: `/sport`, `/sports/`, `/entertainment/`, `/lifestyle/`, `/business/markets`, `/opinion/`, `/editorial`, `/obituaries/`, `/travel/`, `/recipes/`, `/horoscope`.
  - `min_reliability` against `source_reliability.json`, extended with domain keys. Unknown outlets get `DEFAULT_SOURCE_SCORE`.
  - Checked against the NewsAPI `source.name` and URL domain, and the GDELT SOURCEURL domain. Rejections carry reason `blocked_outlet` or `blocked_section`.

**NewsAPI** (and multilingual): accept only if **all** of the following hold:
- an **actor signal**: an Actor roster name, a country name or demonym, or a political/military role term (`government|minister|president|prime minister|parliament|military|army|navy|air force|troops|rebels|militants|insurgents|junta|NATO|UN|EU|ceasefire|embassy|diplomat|sanctions`);
- an **action signal**: a `CRISIS_KEYWORDS` hit, word-boundary matched;
- **no** hit on the negative-topic lexicon (sports: match/tournament/league/cup/Grand Prix/F1/goal/coach; entertainment: album/film/box office/celebrity/concert/series; markets: earnings/shares/stock/IPO/quarterly; lifestyle/weather; history: "anniversary", "in 19xx", "years ago", "history of"), unless the actor signal is strong (≥2 distinct state actors).

Type assignment keeps first-match order but runs on the regex hits. Multilingual queries get a per-language keyword and negative-topic list in config (es/fr/pt/ar/ru).

**GDELT strict keep rules** (`gdelt_rules` in config):
- `IsRootEvent == 1` and `NumArticles ≥ 1`.
- CAMEO **base codes**, 3-digit, with verbal-conflict codes (QuadClass 3) restricted:
  - *Standalone-eligible*: 138 (threaten with military force), 150-155 (force posture / military alert / mobilization), 160-166 only if interstate (reduce relations, sanctions, expel diplomats), 172-175 (coercion: arrests/deportation of political actors, repression), 180-186 (assault: abduction, bombings, assassination), 190-196 (conventional force: blockade, occupy, fight, aerial, violate ceasefire), 200-204 (mass violence/WMD).
  - *Interstate only*: 100-129, 130-137, 139 (demands, disapproval, rejection, threats). Both actors must be states of *different* countries.
  - *Dropped*: 140-145 protests unless `NumArticles ≥ 5` or an actor type in {OPP, GOV}; 170-171 and generic 1-digit/"0"-suffix vague codes when Actor2 is blank.
- **Actor rule:** at least one actor must be geopolitical. Accepted Type1Code values: `GOV, MIL, REB, INS, SEP, OPP, IGO, UAF, SPY, LEG, PTY`. A blank type counts as geopolitical only when the actor code is a bare country code (Actor1Code == Actor1CountryCode, e.g. `RUS`), meaning the state itself. Reject when every present actor is typed as `CRM, COP, JUD, MED, EDU, BUS, CVL, LAB, REF, AGR, HLH, ELI` and no geopolitical actor is present (`non_geopolitical_actors`). Reject events with no actors at all.
- **Corroboration:** standalone events need `NumSources ≥ 2` or `NumArticles ≥ 3` after URL collapse and clustering, *except* 190-204 with a MIL/REB/INS/UAF actor. Otherwise reject (`uncorroborated`, counted in the report so the threshold can be tuned).

**ACLED:** drop `sub_event_type` in {"Peaceful protest", "Other", "Change to group/activity", "Headquarters or base established", "Looting/property destruction"} when fatalities == 0. Also drop "Strategic developments" unless the sub-type is in {Agreement, Arrests, Disrupted weapons use, Non-violent transfer of territory} with a state actor. Keep all events with fatalities ≥ 1.

---

## 3. Duplicates (`dedup.py`, schema)

**Stable ids and URL canonicalization (normalize.py)**
- Canonical URL = lowercase host, strip `www.`, `utm_*`, `fbclid`, `gclid`, `amp`, `/amp` and fragments, drop the trailing slash.
- NewsAPI id = `news_` + sha1(canonical_url)[:16]. This fixes the per-outlet-per-day collision.
- Store the full URL in a new `source_url` (Text) column instead of `source_id` String(100).

**Stage A, within one source batch:**
- GDELT: group rows by canonical SOURCEURL and keep **one representative per URL**. Choose it by consistent geo first, then highest base-code tier (20 > 19 > 18 > 17 > 15 > 16 > 13…), then best precision (city > region > country), then most NumArticles. Record `num_rows_collapsed` in the report.
- NewsAPI/multilingual: skip exact canonical-URL repeats across queries and languages.

**Stage B, cross-source clustering** (batch + active DB rows):
- *Blocking key*: `(country_code, type_family)`, where `type_family` ∈ {armed_conflict: conflict/military/proxy/terror, unrest: civil_unrest/leadership_change, political: diplomatic/alliance/economic/trade_war/sanctions, other}.
- *Candidate window*: `|date_start Δ| ≤ 48h` (ACLED is daily, so its window is [day − 1, day + 1]).
- *Match* if **either** holds:
  - (a) both are city or point precision, distance ≤ 50 km, and title similarity ≥ 0.35; or
  - (b) title similarity ≥ 0.6 (any precision within the country); or
  - (c) same canonical URL.
- *Title similarity*: Jaccard on normalized token sets (lowercase, cleaned title, stopwords and source names removed, numbers kept, simple stemming by stripping `s|ed|ing`). Named entities (country, city, actor names) count double.
- *DB side*: for each blocking key present in the batch, load active rows from the last 72h with one query (index on `(is_active, country_code, date_start)`). Comparisons stay within a block, so the cost is roughly the sum of bucket sizes squared, fine at ~1k candidates/hour.

**Merge semantics** (no duplicate Crisis rows are created):
- *Primary* = existing DB row if matched. Otherwise, within a new cluster, pick by source priority ACLED > curated news outlet (reliability ≥ 85) > other news > GDELT, then best precision, then longest clean title.
- On merge:
  - increment `source_count`;
  - add a row to the new `crisis_sources` table (`crisis_id, source, external_id, url, outlet, title, published_at`, unique on `(crisis_id, url)`);
  - update `last_seen_at`;
  - upgrade location only if the newcomer has strictly better precision and passes validation;
  - replace the title only if the new one scores better (not synthesized, from a higher-reliability outlet);
  - take `severity` = max(existing, new) for fatality-backed sources, and recompute `global_impact` from the merged evidence.
- The primary keeps its id, so `CrisisSnapshot`/`Forecast`/escalation history stays attached.
- Merges invalidate the `crises:` cache prefix at the end of the sync (the scheduled sync doesn't clear it today).

**Lifecycle / expiry:** at the end of each sync, set `is_active=False` where `last_seen_at` is older than a per-source TTL: GDELT 3 days, NewsAPI 7 days, ACLED 30 days. `CURATED`/`status='upcoming'` rows and manually verified rows are exempt. `snapshot_severity_history` already only reads active rows.

**Schema** (models.py plus one Alembic migration after `e8201ea25035`):
- `crises` gains `source_url` Text, `country_code` String(3), `location_precision` String(10), `source_count` Integer default 1, `last_seen_at` DateTime, `global_impact` Integer default 0, and `scoring_factors` Text (JSON breakdown).
- Indexes on `(is_active, country_code, date_start)` and `last_seen_at`.
- New `crisis_sources` table.
- `to_dict()` adds `country_code, location_precision, source_count, global_impact, source_url, severity_band, impact_band`.

---

## 4. Severity → two scores (`scoring.py`)

Both scores are 0-100, deterministic, and stored with their breakdown in `scoring_factors`. There is one shared band function, used in the backend (`app.py` briefing, economic impact and alerts thresholds) and mirrored in the frontend: **critical ≥ 80, high ≥ 60, elevated ≥ 35, low < 35.**

**`severity`: local intensity** (how violent or serious on the ground)
```
base by event class: verbal/diplomatic friction 10 · threat/sanction/expulsion 20 · protest 15
  (violent riot 25) · force posture/exercise/mobilization 25 · repression/arrests 25 ·
  assault/bombing/assassination 40 · armed clash 45 · aerial/artillery strikes 50 ·
  mass violence / WMD / coup 60
+ fatalities: 0 → 0 · 1–4 → 8 · 5–24 → 15 · 25–99 → 25 · 100–499 → 32 · 500+ → 40
+ scale words (word-boundary, one max): "dozens" +5, "hundreds" +10, "thousands displaced" +8
caps: verbal ≤ 30 · protest without fatalities ≤ 40 · single unverified news/GDELT source ≤ 65
```
- Fatalities come from ACLED `fatalities`.
- News uses the regex `(\d{1,5}|dozens|hundreds)\s+(?:people\s+|civilians\s+|soldiers\s+)?(?:were\s+)?(killed|dead|died)`, with small word-numbers ("two", "three" …) mapped too.
- GDELT has no fatalities, so it gets the event-class base plus scale words only if the URL slug contains them.

**`global_impact`: international significance** (drives globe emphasis, critical badge and default sort)
```
start: min(severity, 50) × 0.4                          (local intensity contributes, capped at 20)
+ interstate (parties from ≥2 different countries, at least one state/military) +20
+ direct military action between states (190–204 or ACLED Battles with two state forces) +15
+ nuclear-armed state as a party (Actor.is_nuclear) +12; two nuclear states +20 total
+ great power party (US, CN, RU, EU members via roster) +8
+ strategic location (config list: Strait of Hormuz, Taiwan Strait, Bab-el-Mandeb, Suez,
  Malacca, Black Sea, South China Sea, Baltic, Korean DMZ; matched by bbox or name) +8
+ corroboration: source_count ≥3 +3 · ≥10 +6 · ≥25 +10
+ escalation terms (word-boundary): "declares war", "invasion", "nuclear test", "ballistic missile" +10
caps: purely domestic (one country, no foreign party) ≤ 55 · single source ≤ 60 · verbal-only ≤ 50
≥ 80 requires at least two of {interstate, nuclear-state party, ≥100 deaths, source_count ≥ 10}
```

**Targets** (checked by a distribution test on the fixture set and shown in the pipeline report): `global_impact` critical ≤ 5% and high ≤ 15% of active events. `severity` critical ≤ 10%.

Weights live in `event_filters.json → scoring` so they can be tuned without code changes.

---

## 5. Titles (`titles.py`)

`clean_title(raw, outlet_name, url) -> str | None`, with explicit patterns:
- **Source suffix:** `r'\s*[-–—|:•]\s*(?:{outlets})\s*$'`, where `{outlets}` = re.escape of the NewsAPI `source.name`, the domain stem and the config `known_outlets` list. Repeat until no match. Also strip `r'\s*\((?:Reuters|AP|AFP|Bloomberg)\)\s*'`.
- **Leading tags:** `r'^(?:BREAKING|LIVE(?: UPDATES?)?|UPDATE\s*\d*|WATCH|EXCLUSIVE|OPINION|ANALYSIS|EXPLAINER|VIDEO|PHOTOS)\s*[:\-–|]\s*'` (case-insensitive).
- **Date fragments:**
  - `DATE = r'(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?(?:\d{1,2}\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?(?:\s+\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}'`
  - Strip `^DATE\s*[:\-–|,]\s*` and `\s*[:\-–|,]\s*DATE$`.
  - Strip "Day \d+ of …" live-blog tags.
- **Reject (→ synthesize)** if, after cleaning:
  - the remaining text fully matches `DATE` or the ID pattern `^[A-Z]{2,4}\d{3,}$`;
  - it has fewer than 4 words or fewer than 20 characters;
  - it is generic (`^(news|home|latest|live|top stories|headlines)\b`);
  - it is a URL.
- **Normalize:** collapse whitespace, strip wrapping quotes, title-case ALL-CAPS headlines (keeping acronyms from a whitelist), and truncate at a word boundary to 200 characters with "…".

**Synthesis fallbacks**
- **ACLED:** `f"{sub_event_type} in {location}, {admin1}"`, with `: {n} killed` appended when fatalities > 0. Example: "Armed clash in Pokrovsk, Donetsk: 4 killed".
- **GDELT:**
  1. URL slug headline: take the last path segment, drop IDs, dates and extensions, and require ≥4 alphabetic words, e.g. "5 Miners Killed, Others Injured in Plateau Attack".
  2. Otherwise a CAMEO template: `"{Actor1} {verb phrase} {Actor2} in {place}"`, e.g. "Russian military conducts aerial strikes on Ukraine near Kharkiv". Actor names are title-cased; a missing actor is replaced by the country's demonym plus "forces" or "government" by type.
- **NewsAPI:** the first sentence of the description (dateline stripped), cleaned by the same rules. If that fails too, reject (`no_usable_title`).

---

## 6. Frontend (`app.js`, `frontend-api.js`, `index.html`)

- One `normalizeCrisis(c)` used by `loadRealData` (~3354), deep links (~2899) and the websocket `new_crisis` handler (~3468). It keeps `source`, `source_count`, `location_precision`, `country_code`, `global_impact`, `severity_band` and `impact_band`, and drops items with null or invalid coordinates instead of `|| 0`.
- A defensive client-side dedup by `id` at load.
- One `band(score)` helper plus the colour map, replacing the 7 hard-coded `>80/>60` copies (877, 1787, 2262, 2537, 2954, 4223, 4350). This also fixes the `>80` vs `>=80` inconsistency.
- Alert badge (~2805) counts `global_impact ≥ 80` over the *filtered* set. The list row shows the severity badge plus an impact marker and "N sources" when `source_count > 1`.
- Default ordering is by `global_impact` (backend `ORDER BY global_impact DESC, severity DESC`).
- Remove the ring-spread (~1709-1737) and rely on the existing cluster bubbles, so pins stay at their true coordinates.
- Country-precision events render as a hollow, larger, low-alpha marker (reusing the dashed "upcoming" style at ~1850) and are excluded from the heatmap.
- The country filter compares `c.country_code` to the topojson id instead of name strings (1679, 2232, 1216).
- Delete the dead `CITY_COORDS`/`getRandomCityCoords` (354-655).

---

## 7. Observability, backfill and cleanup

- **PipelineReport** is logged at INFO after each sync and stored in memory (last 24 runs). `GET /api/admin/pipeline-report` (admin auth, same decorator as `/api/admin/sync`) shows kept/merged/rejected counts by source × reason plus band histograms. This is how thresholds get tuned.
- **`backend/scripts/preview_pipeline.py [--source gdelt|newsapi|acled] [--limit N]`** fetches live data and runs the pipeline with **no DB writes**. It prints counts, rejection samples per reason, the score distribution and 20 sample titles.
- **`backend/scripts/reprocess_crises.py [--dry-run]`** runs every active row through normalize → relevance (on stored fields) → location → titles → dedup → scoring. It deactivates rejects and merged duplicates (`is_active=False`, **never deletes**, so snapshot and forecast history survive) and backfills the new columns. The default is dry-run, which only prints the plan.
- **Remove** the dead AI geocoding path and the `claude-3-5-sonnet-20241022` use in `data_sources.py`. (The three `app.py` briefing calls using the same retired model are out of scope and flagged separately.)
- `before_request` sample seeding (app.py:2579) keeps working unchanged. Sample rows go through normalize via `reprocess` so `country` values like "Kyiv" are fixed.

---

## Implementation phases (each a small, independently shippable PR)

0. **This document** (`docs/EVENT_FILTERING.md`).
1. **Bug fixes + scaffolding:** word-boundary keyword matching, stable NewsAPI URL ids, route multilingual through `_upsert_crisis`, remove the dead AI geocoder, `event_pipeline/` skeleton with `process_batch`, `PipelineReport`, `event_filters.json`, `preview_pipeline.py`.
   *Tests:* `test_relevance_keywords.py` (said/software/Warsaw/heart attack regressions), NewsAPI id stability and no collisions.
2. **Titles:** `titles.py` and `cameo_titles.json`, wired into all three connectors.
   *Tests:* `test_titles.py` (suffix/prefix/date/ID cases, ACLED/GDELT/news synthesis, 200-character truncation).
3. **Relevance + outlet filtering:** NewsAPI actor+action+negative lexicon, outlet/section blocklist, GDELT strict rules, ACLED sub-type rules.
   *Tests:* `test_relevance.py` with fixtures from the live failures (F1/Baku, 1934 cruise, Taylor Swift/Washington, grooming-gangs op-ed), `test_gdelt.py` updates via `make_row` (IsRootEvent, actor types, codes, corroboration).
4. **Locations:** `countries.json`, `geo.py` polygon check, `gazetteer.json`, GDELT actor-geo consistency, news resolver (metonymy, ambiguous names, scoring).
   *Tests:* `test_location.py` ("Washington sanctions Venezuela" → Venezuela at country precision, "Victoria" without Seychelles → rejected, politico Berlin/Miami → Miami rejected, point-in-polygon incl. coastal tolerance, country alias normalization).
5. **Schema + dedup/merge + expiry:** models, Alembic migration, `crisis_sources`, URL collapse, clustering, merge, TTL deactivation, cache clear after sync, `reprocess_crises.py`.
   *Tests:* `test_dedup.py` (same article in 18 GDELT rows → 1; Reuters and AP versions of the same story → 1 row with source_count 2; different events same city same day with dissimilar titles → 2; merge keeps primary id and snapshots; expiry respects exemptions).
6. **Scoring:** `scoring.py` with the two scores, shared bands, `app.py` thresholds switched to the band helper, `to_dict` fields, ordering by `global_impact`.
   *Tests:* `test_scoring.py` (rubric cases, caps, the ≥80 two-condition gate, a distribution test on a ~200-event fixture asserting ≤5% critical impact); update `test_gdelt.py` severity assertions.
7. **Frontend:** `normalizeCrisis`, `band()`, badge on `global_impact`, remove ring spread, precision markers, country_code filter, "N sources".

---

## Critical files

- `backend/data_sources.py`: connectors emit `_meta`; `DataAggregator.sync_all_sources` / `_upsert_crisis` call `event_pipeline.process_batch`; AI geocoder removed.
- `backend/newsapi_multilingual.py`: route through the pipeline and upsert.
- `backend/models.py` + `backend/migrations/versions/<new>_event_quality_fields.py`
- `backend/app.py`: `/api/crises` ordering, band helper in briefing/impact/alerts, `/api/admin/pipeline-report`, cache clear in `scheduled_sync`.
- New: `backend/event_pipeline/*`, `backend/config/{event_filters,countries,gazetteer,cameo_titles}.json`, `backend/config/geo/countries-50m.json`, `backend/scripts/{preview_pipeline,reprocess_crises}.py`, `backend/tests/test_{titles,relevance,location,dedup,scoring}.py`.
- `app.js`, `frontend-api.js`.

Reuse: `NewsBasedCrisisDetector._find_stakeholders` (actor matching), the `DATELINE_RE` idea, `DataAggregator._upsert_crisis`, the `source_reliability.json` loader in `app.py:165`, the `cache_clear_prefix` helper, `make_row` in `tests/test_gdelt.py`, and conftest fixtures.

## Verification

1. `cd backend && pytest -v`: all new and updated tests pass, as in CI (`.github/workflows/backend-tests.yml`).
2. `python scripts/preview_pipeline.py --source gdelt` on a live file. Expect about a 90% reduction versus 186 kept per 15-minute file, at most 1 event per URL, no F1/history/sports items, and ≤5% `global_impact ≥ 80`. Repeat for `--source newsapi` with a key, and inspect the rejection samples per reason.
3. `alembic upgrade head` on a copy of the DB, then `python scripts/reprocess_crises.py --dry-run`, review the output, then run it for real.
4. Run the app (`/run`). On the globe: no ring-spread pins crossing borders, country-level markers visibly distinct, clicking a country filters by code, list titles have no dates or outlet suffixes, "N sources" shows on merged events, and the critical badge count is small and changes with filters.
5. Check `GET /api/admin/pipeline-report` after one scheduled sync to confirm counts per reason.
