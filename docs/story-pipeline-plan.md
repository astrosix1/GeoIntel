# Story pipeline: one story, one pin

Plan for making pins accurate, severity strict, analysis deep, scenarios grounded and duplicate articles merged with every source named. Earlier phases are in `docs/roadmap-phases-1-21-archive.md`.

## What the owner asked for, and what was decided

Five things: pins in their accurate location, a **strict severity scale**, **deep analysis**, **scenario branching**, and a **strict article filter** that cuts duplicates and merges very similar articles into one story that names all its sources.

Decisions:
- **Severity:** five written levels. The AI only extracts facts from the article; plain code turns the facts into the level and the number.
- **Merging:** two tiers. Free rules for the clear cases, a cheap AI check only for borderline physical pairs.
- **Build order:** four stages, each checked before the next.

## The idea that makes it efficient

The unit of work becomes the **story** (a merged group of articles about one event). Every expensive step runs **once per story**, in cost order: free rules first, then a small cheap model, then the large model only when a user asks. Each result is **recorded in the database so it is never repeated**.

Today every step runs per event, a third of the events are duplicates, several steps make their own AI call, and the extra articles' sources are thrown away.

## What the data and code show

From the last 3 days (3,772 global events):
- 33% of events use an article that another event already uses; 32% repeat an exact headline; 28% share their first five key words.
- The three existing caps in `data_sources/gdelt.py` (`_cap_fanout_per_source_url`, `_per_event_cluster`, `_per_title_day`) **drop** the extras, so their sources are lost.
- 96% of events carry one source (`NumSources` = 1), so the grouping must be done by us.
- Severity is `-Goldstein x 10` (`GDELTConnector._parse_row`). That scores how violent the verb is, not how big the event is. 14% of events are exactly 100 and 22% are 90+; "5 miners killed" and "2nd source alleges Netanyahu knew" both score 100.
- `services/briefing.py` already builds numbered, citable sources from `News` rows attached to an event (`News.crisis_id`), and the detail and related endpoints already return them. **Nothing fills them for GDELT today**, so merged articles written as `News` rows reach the briefing with little change.
- `services/location_refine.py` makes its own AI call to name the place. The new extraction call replaces it, so one call serves location, severity and analysis.
- Comments, saved events, alerts and the scenarios cache are keyed by crisis id, so **a merged story keeps the earliest event's id** and nothing keyed to it breaks.

## Stage 1: merge into stories and name every source (free, no key)

- **Migration:** `crises.merged_into` (String 50, null, indexed) and `crises.source_count` (int, default 1). A merged duplicate is kept but set `is_active = false` and `merged_into` points at the primary, so it is reversible.
- **New `services/stories.py`:**
  - *Tier 1, clear cases, pure code.* Same normalised article URL (strip scheme, `www`, query, fragment, trailing slash); same normalised headline; or significant-word similarity of at least 0.6 between headlines **and** the same country, `event_kind` and location (within about 11 km) with dates within 1 day. The primary is the earliest event, ties broken by confidence.
  - *Tier 2, borderline pairs.* Physical events only, same constraints, similarity 0.35 to 0.6: a small-model yes/no on the two headlines. Each verdict is stored in `story_merge_checks` so a pair is judged once, with a per-run cap. Never merges across countries or events more than 2 days apart.
  - Each merged article becomes a `News` row on the primary (outlet, title, url, `published_at`). `source_count` is the number of distinct outlets and replaces the `NumSources` confidence formula.
- **`data_sources/gdelt.py`:** replace the three drop-the-extras caps with `merge_batch` before the upsert (merge, don't discard). `scheduled_sync` also runs `merge_recent(days=3)` for late arrivals. Update `test_gdelt.py`.
- **`blueprints/crises.py`:** the lean list adds `sources` (only when above 1); `GET /api/crises/<id>` follows `merged_into` to the primary so old links and saved ids still open; the detail's `news` lists every source.
- **Frontend:** pins, popups and stacked lists show "N sources". The Analysis panel gets a **Sources** section listing every outlet with its headline and link.
- **Backfill:** a one-off, idempotent script over the last 7 days.

## Status

- **Stage 1 (merge, name every source): implemented.** Dev data: 10,882 events became 2,368 stories after merging 2,422.
- **Stage 2 (facts per story): implemented.** `crises.article_excerpt/facts/facts_extracted_at` (migration `d4b7e9a1c836`), `services/story_facts.py`, excerpt from the same page fetch, `location_refine` now reads `facts.place` (batch order: most sources, then newest). Needs `ANTHROPIC_API_KEY` to run.
- **Stage 3 (strict severity): implemented.** `services/severity.py`, columns `severity_level/severity_basis` (migration `e2a6c8d4f917`), scored on ingest, after merging and after facts; `python -m services.severity` rescored the dev data (headline-only rows now top out at 59, so none are Severe/Critical until facts are extracted). Frontend: five bands, Major = 60+, "Why this rating" list.
- **Stage 4 (analysis and scenarios over the story): implemented.** Briefing and scenario prompts now include the extracted facts, the severity reasons, the saved article excerpt and (briefing) up to 20 sources; the briefing is told to say where sources disagree. Cached results carry a `story_stamp` (source count + facts time), so a new merged source or new facts rebuilds them. Gating, limits and the no-numeric-probability check are unchanged.

## Stage 2: one extraction call per story (place and facts)

- **`data_sources/utils.py`:** `fetch_real_page_metadata` also returns a short body excerpt (about 1,500 characters of visible text) from the **same request** already made for the headline. New column `crises.article_excerpt`.
- **New `services/story_facts.py`:** one small-model call per story (new `AI_FACTS_MODEL`, Haiku by default, env `ANTHROPIC_FACTS_MODEL`), forced tool use, returning only:
  - the specific `place` and `country`, `is_statement`, `event_type`
  - `killed` and `injured` (integers, or null)
  - scale cues from a fixed list: mass casualty, infrastructure, chemical/biological/nuclear, state actors, ongoing
  - a one-line `summary` and a `confidence`
- **Validation** as in `services/scenarios.py`: fixed lists only, bounded non-negative integers, and **null rather than a guess** when the article doesn't state a number. Stored in `crises.facts` (JSON) with `facts_extracted_at`. A definite "nothing usable" is recorded; a temporary failure is not.
- **`services/location_refine.py`** reads `facts.place` instead of making its own AI call. The Nominatim lookup, same-country check and recording rules stay.
- **Scheduler:** the `location_refine` job becomes `story_enrich`, a capped, priority-ordered batch (physical first, then most sources, then newest; env `STORY_ENRICH_PER_RUN`, default 60 per 20 minutes) that stops early when the AI or geocoder looks down.

## Stage 3: strict severity, scored by code and shown with reasons

- **New `services/severity.py`:** a pure function from facts to `{level, score, basis[]}`. The AI never outputs the number.
- **Written scale (shown in the UI):** Minor 0-19, Moderate 20-39, Serious 40-59, Severe 60-79, Critical 80-100.
- **Rules**, all in one table so they can be read and tuned:
  - statements and talks are capped at Serious (49) and scored by the feed's verb intensity
  - physical events with no stated casualties score 20-55 by type
  - stated deaths set a floor: 1-2 killed 55, 3-9 killed 65, 10-99 killed 80, 100+ killed 90; injuries add smaller floors
  - mass-casualty or chemical/biological/nuclear cues floor at 90
  - corroboration adds up to +10, and **Critical needs two or more independent outlets**
  - with no extracted facts the score is a headline-only estimate **capped at Serious**, and it says so
  - the basis quotes what the article states, for example "5 killed, stated in the article" or "reported by 4 outlets"
- **Columns:** `severity_basis` (JSON) and `severity_level` (1-5). Ingest computes a provisional headline-only score, replaced when facts arrive. `severity` stays the stored number, so lists, filters, colours, alerts and saved events keep working. Frontend labels and colours move to the five bands, and "Major" becomes Severe and above (60 or more).
- **Analysis panel:** a level badge and a **Why this rating** list.

## Stage 4: deeper analysis and scenarios over every source

- `services/briefing.py` and `services/scenarios.py` build their context from the story: the extracted facts, up to five source excerpts (the `News` rows), and every source as a numbered citation. The model is told to cite only those and to say where sources disagree.
- Cache keys gain `source_count` and a facts hash, so a story is re-analysed when a new source merges in.
- Gating, rate limits, premium rules and the "no numeric probabilities" check are unchanged. Analysis and scenarios stay on-demand and cached on the large model; only the small model runs in bulk.

## Cost

About 700 stories a day after merging, against about 1,250 events a day now. Bulk work is one small-model extraction per story, roughly 1,000 tokens in and 250 out, which is on the order of $1.5-2 a day (about $45-60 a month, to be rechecked against real pricing), plus a few borderline-pair checks. Everything is capped per run, idempotent and resumable.

## Testing each stage

- Unit tests per stage: normalisation, similarity and merge rules, tier-2 caching and cap, extraction validation with a fake client, the severity table row by row (including the caps and "headline only"), and briefing and scenario prompts containing every source.
- Migrations run on a copy of the dev database; the full backend suite, `tsc`, lint and the build stay green.
- Before and after on the dev data: events to stories (roughly a third fewer rows), the severity histogram (no more 22% at 90+), merged stories listing all sources.
- Live, with a scratch launcher: a fake AI client driving real article fetches and real Nominatim for stage 2, then the browser check of the source counts, Sources list, level badge, "Why this rating", moved pins, and a premium briefing that cites every source.

## Owner actions

- Stage 1 and the headline-only part of stage 3 need no key. Stages 2 and 4 need `ANTHROPIC_API_KEY`.
- Run each stage's migration in production.

## Out of scope

Embedding-based clustering, cross-language de-duplication, a user-facing unmerge control, and moving existing Supabase comments onto the primary when two stories merge (comments on a merged-away id stay on that id; the detail endpoint redirects readers to the primary).
