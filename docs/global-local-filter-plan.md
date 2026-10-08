# Global and Local news filters

Plan for deciding which events belong under **Global** and which under **Local**, using the owner's two term lists (Global: institutions, geopolitics, economics and markets, health and environment, science and space, scale words; Local: municipal governance, infrastructure, education, community, local business, local services, transport, civic groups, local health, scale words). Nothing here is built yet.

## How it works today

- `crises.scope` is `'global'` or `'local'`, set once at ingest in `GDELTConnector._parse_row`.
- It is **not** based on topic. An event is `local` only when GDELT's actor data looks like routine domestic noise: a generic actor name, the same actor on both sides ("United States criticizes United States"), or a blank actor under a violence code.
- Everything else, including all NewsAPI and curated rows, is `global`.
- On the dev data that gives **10,181 global and 1,747 local** (85% / 15%). The global list is full of local stories ("Michigan man faces 12 felony charges", "Urban Decay Turns Canter's Deli Into a Rave"), and the local list holds items that are not local (a presidential rally, a South African disciplinary hearing).
- The toggle sends `?scope=global|local` to `/api/crises`, which filters `Crisis.scope`. The frontend needs no change if the stored scope becomes right.

## The idea

Replace the actor-noise guess with a **topic classifier** built from the two lists, run on what we know about each event: the headline, the extracted facts and article excerpt when they exist (story pipeline, stage 2), the country and the refined place name. The result is stored in `crises.scope`, so the list, the globe, alerts and saved events keep working unchanged.

The term lists live in data, not code: `backend/data_sources/scope_terms.json` (one entry per term: text, group, side, weight, and a "needs context" flag). The owner can edit them without touching the classifier.

## Matching rules

1. **Whole words and phrases, case-insensitive.** "UN" must not match "fun", "EU" must not match "queue", "ICC" must not match "icc".
2. **Acronyms are matched case-sensitively** (UN, EU, WHO, IMF, ICC, G7, NASA, AI) and only as standalone tokens, because "who", "ai" and "un" are ordinary words in several languages.
3. **Weights.** A named institution or market (IMF, NATO, Brent, OPEC) is a strong global signal. A scale word ("global", "worldwide") is a medium one. Words that are only global in context ("war", "conflict", "terrorism", "pandemic", "AI", "climate") are weak on their own and count only with a second signal or a foreign country/actor pair.
4. **Local words are weak by default** ("police", "crime", "park", "school", "street", "festival" occur in global stories too). They count as local when the story has **no strong global signal** and the place is city-scale (a refined place name, or an actor pair that is one country on both sides).
5. **Placeholders** in the owner's local list ("[specific neighborhood names]", "within [city/region] boundaries") cannot be matched as text. They are covered by the place signal in rule 4: the story pins to a named town, suburb or county rather than a country.
6. **Both sides match.** Strong global signal wins ("Mayor attends UN summit" is global). Two or more weak global and two or more weak local signals: use the actor pair (two different states means global, one means local).
7. **Neither side matches.** See decision 1.
8. **Existing actor-noise signals stay** as a hard override to local (they are verified against live data), unless a strong global signal is present.
9. **Languages.** English only at first. The French and Spanish NewsAPI rows keep their current scope until their own term lists exist.

## Decisions (made by the owner)

1. **Events that match neither list keep the side the existing rules give them** (actor noise means Local, otherwise Global).
2. **An "All" view is added** next to Global and Local (the backend already treats a missing `?scope=` as all).
3. **Local events with no usable place are shown under Local**, marked approximate as today.

## Stages

1. **Term data and classifier, no behaviour change.** `scope_terms.json`, `services/scope.py` (pure function: headline, facts, place, actors, country to scope, score and the matched terms), and a report script `scripts/scope_report.py` that runs it over the last 7 days and prints: the new global/local split, how many events match neither, how many change scope versus today, and 40 random changed examples each way. The owner reviews this before anything is switched.
2. **Tune with the owner.** Adjust weights and "needs context" flags from the report. Add tests for every term group, the ambiguity cases in rule 1 to 3, and the both-sides tie break.
3. **Switch on.** Classify at ingest (replacing the actor-noise-only assignment), re-classify the existing rows once with an idempotent backfill, store the matched terms in a new `crises.scope_basis` column (JSON) so each event can say why it is global or local. Migration to run in production.
4. **Show why.** A small "Why Global/Local" line in the event Analysis panel (the matched terms), and the Local-view note updated, since local severity is no longer "unreliable" simply because of noise.
5. **Optional: embeddings or a cheap AI check** for borderline events only, with the verdict stored so a pair is judged once. Only if the report shows the rules leave too many borderline.

## Risks

- **Ambiguity.** "War", "conflict", "AI", "WHO", "crime", "park" and "area" appear in both kinds of story. Rules 2 to 4 are the guard, and the report is how we check it.
- **Headline quality.** Many GDELT titles are page titles with site names ("... | Tenterfield Star | Tenter..."). The site name itself is a useful local signal (regional outlets) but it is not in either list; worth adding a small outlet-type signal later.
- **Volume.** Classification is string matching over about 1,200 events a day; cost is negligible and runs inside the existing ingest.
- **Moving events between toggles** changes what users see overnight. The report in stage 1 is the safeguard.

## Out of scope

Languages other than English, per-user custom term lists, a map-level Local radius, and classifying by outlet reputation.

## Stage 1 as built (no behaviour change yet)

- `backend/data_sources/scope_terms.json`: the two lists as weighted groups (weight 3 strong, 2 medium, 1 weak; acronyms case-sensitive).
- `backend/services/scope.py`: pure `classify(text, place_specific, actors_differ, noise)` returning the scope, the rule that decided it and the matched terms. All weak terms together count as one signal.
- `backend/scripts/scope_report.py [days] [samples]`: runs the classifier over the database and prints the split, the reasons, the busiest terms and random examples of events that would change side. Changes nothing.
- `backend/tests/test_scope.py`: 26 tests.

**First report (last 7 days, 11,554 events):** 77% match neither list and keep their old side; 5% become or stay Global through a term, 3% move Global to Local, 0.4% move Local to Global. The lists decide only a minority of events, so most of the feed is still sorted by the older actor-noise rule. Tuning so far: "General Assembly", "coalition", "accord", "protocol", "alliance", "occupation" and "regional" were demoted to weak because they are ordinary words in national stories.

## Stage 2 as built (tuning)

Changes made after reading the report samples:
- Everyday words became weak (they no longer decide an event alone): coalition, accord, protocol, alliance, occupation, invasion, sovereignty, outbreak, epidemic, pandemic, COVID, coronavirus, heatwave, "General Assembly", "regional", OpenAI. Removed from Local: "area", "court", "crash" (replaced by "car crash", "truck crash", and similar), "city of".
- Market acronyms (WTI, FTSE, DAX, IPO) are case-sensitive; "Brent" became "Brent crude" / "Brent oil" (it was matching a person's name).
- **Place signal:** a pin precise to a city or town (`location_confidence` of 85, which GDELT's own place detail gives) counts as a specific place. With one weak local word (police, arrested, school, theft, county jail) and no global term, the event is Local. This catches the many plain local-crime headlines that match no list term. It is blocked when the two actors are different states, so "Police attacks India"-style actor-pair headlines stay Global. At ingest the real actor pair is known; the report cannot see it, so the report slightly over-counts Local.
- 28 tests.

**Report now (last 7 days, 11,554 events):** 73% stay Global, 14% stay Local (old noise rule), **12% move Global to Local** (9% on the place signal, 3% on local terms), 0.3% move Local to Global. 69% still match nothing and keep their old side.

**Known weak spots:** headlines about a national story that happen to be pinned to a city ("Istanbul school stabbing", "FlyDubai plane crash into Tel Aviv"); "Mayor" in a story about a mayor's foreign-policy statement; and synthetic actor-pair titles, which stage 3 can judge properly because the actors are known at ingest.

## Stage 3 (next)

Classify at ingest with the real actor pair and place precision; add `crises.scope_basis` (JSON of matched terms and the rule); an idempotent backfill over existing rows; the "All" button; migration. Review the stage 2 numbers first, because switching on moves about 12% of current events from Global to Local.

## Stage 3 as built (switched on)

- **Ingest:** `GDELTConnector._assign_scope` runs after the real headline is resolved and classifies with the real actor pair, pin precision and the old noise signal. It stores the verdict in `crises.scope` and the reason in the new `crises.scope_basis` (JSON: rule plus up to 6 terms per side).
- **Existing events:** `services.scope.judge_missing()` judges every row with no `scope_basis`; it runs at every start-up from `scripts/ensure_db.py` (after the migrations), only touches unjudged rows, and never stops the app starting. By hand: `python -m services.scope`. On a copy of the dev database it judged 32,150 events and moved 4,632 (a second run did nothing).
- **Migration:** `a9c3e5b7d142` (adds `scope_basis`), applied automatically on deploy.
- **"All" button** added beside Global and Local; counts add up (Global 2,585 + Local 929 = All 3,514 for two days on the copy).
- **Two more terms dropped from the Local list after checking the data:** "regional" (it was making "Tehran Regional Tensions" Local) and "protest" / "demonstration" (they were pulling national protests Local). They can be added back in `scope_terms.json`.
- **Side effect:** location refinement only reads Global events, so events that move to Local are no longer refined (they are mostly city-precise already).
- NewsAPI and curated events are not re-classified (they keep Global).
- 31 scope tests.

## Stage 4 (next)

A "Why Global/Local" line in the event panel from `scope_basis`, and rewording the Local-view note and the "Unreliable" severity badge, which assumed Local meant GDELT noise.
