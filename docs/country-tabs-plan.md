# Country tabs: deeper and more extensive

Plan for deepening each of the six country tabs (Government, People, Migration, Economy, Security, Geography). Follows `docs/country-analysis-plan.md` (the first revision, now live). Nothing here is built yet.

## Where we are

Each tab today is a thin view over two sources: the CIA World Factbook (text fields, a few shares) and a handful of World Bank / UN figures. Most values are a single number or a sentence, with no history, no comparison and no map context. The goal is that every tab answers "how is this country doing, how has it changed, and how does it compare" with sourced, dated numbers.

## What was verified (live, no key)

| Source | Reachable | What it gives | Notes |
|---|---|---|---|
| World Bank indicators | yes | life expectancy, unemployment, military spend % GDP, remittances, birth rate, GDP and hundreds more, each with a year series | One call can fetch many series for a country; `country/all` gives every country for ranking. The governance (WGI) series were **not** found under the usual codes; V-Dem via OWID replaces them. |
| UNHCR Refugee Statistics API | yes | refugees, asylum seekers, IDPs, stateless, by country of origin and of asylum, by year | Open, CC BY 4.0. |
| IPU Parline | yes | parliament chambers, seats, women's share, elections | Open data. |
| Wikidata | yes (API and SPARQL) | head of state/government, memberships (UN, NATO, EU...), agencies, cities | Needs careful queries; labels sometimes missing. |
| Wikipedia REST/extracts | yes | summaries and intros for "Politics of X", "Geography of X" | CC BY-SA: needs attribution on screen. |
| Our World in Data (CSV) | yes | energy mix (9 MB file, bundle a subset), V-Dem electoral democracy index, military spend share | CC BY. |
| UNDP HDI annex (xlsx) | yes | Human Development Index and its parts, trends | Static yearly file; bundle. |
| UN DESA migrant stock | yes (have it) | stock by origin and destination, **1990-2024** | We kept only 2024 and the top 15; keeping all years gives trends, and inverting it gives emigration. |
| CIA World Factbook | yes (have it) | far more than we show: land boundaries with lengths, climate, terrain, elevation, natural hazards, land use, coastline, water, environment issues, urban areas, languages, military, energy, communications | Public domain. |
| USGS Mineral Commodity Summaries | partly | production and reserves by country (the real "rare minerals" data) | The data release exists on ScienceBase; the file layout needs checking in stage 1. |
| IMF DataMapper, World Bank Climate portal | **no** (403 / bot wall) | | Skip. |
| UCDP conflict API | needs a free token | georeferenced conflict events and deaths | Optional (decision 4). ACLED stays out. |
| UK travel advice (GOV.UK content API) | not probed | risk level and text per country | Check in stage 3. |

## Tab by tab

### Government
Add: **political system quality** (V-Dem electoral democracy index with its trend); **parliament** (chambers, seats, women's share, last election, from IPU); **leaders** with a short timeline of recent heads of government (Wikidata) and cross-check against the Factbook; **international memberships** (UN, NATO, EU, BRICS, G20, OPEC and so on, Wikidata); **key agencies** (foreign ministry, central bank, intelligence, defence, electoral body) from Wikidata; a plain-language **"how power works"** panel (who appoints, who can veto, who can dissolve) written by the AI only from the Factbook's own executive, legislative, judicial and constitution text, with the text shown beside it; link out to the constitution text. Dropped: scores we cannot source (corruption, press freedom) until a keyless file is found.

### People
Add: **life expectancy, fertility, population growth, urban share, density, dependency ratios, literacy and schooling, HDI with its three parts** (WB and UNDP); **age and sex pyramid** from the Factbook's age bands (finer 5-year bands only if a UN population file is bundled, decision 1); **languages with shares and official status**; **major cities with populations**; **population trend** (30-year series from WB); religion and ethnicity as now. Each number gets its year, its trend arrow where a series exists, and a rank among 190 countries.

### Migration
Add: **trend since 1990** (migrant stock series), **emigration** (where this country's citizens live, with counts, from inverting the UN table), **refugees and asylum** from UNHCR (hosted refugees by origin, asylum applications, refugees and IDPs this country produces, stateless people), **remittances** received and sent (WB), net migration series, and the share of the population that is foreign-born over time.

### Economy
Add: **headline indicators with 10-year series** (GDP, GDP per capita, growth, inflation, unemployment, government debt, current account, FDI, poverty, inequality), **sector shares** (agriculture, industry, services), **energy mix and electricity access** (OWID, bundled), **critical and rare minerals with production and reserves** (USGS, stage 1 check), exports and imports with partner shares as now, plus exports as a share of GDP. Each metric shows rank, year and source. The OEC commodity list stays "unavailable" (no key); the Factbook lists fill that gap honestly.

### Security
Add: **our own events as a trend** (90-day daily series by type, the most affected places within the country, using the refined place names) in place of the single 30-day count; **military**: spend % GDP and in dollars, armed forces size (WB), alliances (memberships); **displacement** (UNHCR); **travel advisory** level from official advisories if the GOV.UK feed works; Factbook terrorism, forces and disputes. Optional with a free UCDP token: yearly conflict deaths and active conflict names.

### Geography
Add (most of this is already in the Factbook file and simply not shown): **location and borders with lengths and neighbours**, **climate, terrain, elevation extremes, natural hazards, land use shares, coastline and maritime claims, water resources, environment issues**, **area and rank**, time zones, capital with coordinates, **live hazards in the country** from our own GDACS weather data, and a short Wikipedia intro with attribution. The AI narrative is rewritten to use these facts.

## Cross-cutting design

- **Per-tab endpoints** (`/api/countries/<cc>/government`, `.../people` and so on, premium as now) so a tab only loads its own data; the free profile stays as is. Cache each for 24 hours; the events part for 15 minutes.
- **Indicator helper:** one function fetches a World Bank indicator set for a country as series with year and source, and one cached call per indicator gives every country's latest value so ranks ("7th of 190") cost nothing extra.
- **Bundled datasets** (UN migration all years, OWID energy subset, HDI, USGS) built by scripts in `backend/scripts/` into `backend/data/country/`, same pattern as `build_migration_data.py`. Each carries its source, year and licence.
- **Honest data:** every value has a year and a source; missing means "not published", never a guess. Wikipedia text is shown with its licence and link.
- **Frontend kit:** a `Stat` row (value, year, source, rank, trend arrow), a small SVG `Sparkline`/line chart, share bars (have), a simple pyramid. Split `CountryDetail.tsx` into one file per tab.
- **AI "analyst read" per tab** (decision 2): a short grounded paragraph per tab, cached for a week, written only from the numbers on that tab and saying where data is missing.

## Stages

0. **Foundation:** per-tab endpoints, indicator helper with series and ranks, shared UI pieces, the Stat/Sparkline kit, split the component. No new data yet beyond what is shown.
1. **Economy and People** (World Bank heavy): indicators with trends and ranks, HDI, energy mix, minerals.
2. **Migration:** all-years UN table, emigration, UNHCR, remittances.
3. **Security:** event trend and hotspots, military figures, displacement, advisories.
4. **Government:** V-Dem, IPU Parline, Wikidata leaders/memberships/agencies, "how power works".
5. **Geography:** full Factbook geography, live hazards, Wikipedia intro.
6. **AI analyst reads and polish:** per-tab paragraphs, loading and empty states, accessibility pass, mobile layout.

Each stage is verified in the browser with at least three very different countries (a large democracy, a small island state, a country in conflict) and ends with tests and the usual commit.

## Risks

- **Latency:** many sources per tab. Batched calls, caching, bundling and per-tab loading keep it quick; first load of a cold country may take a few seconds.
- **Wikidata gaps:** agencies and leaders are uneven. Anything missing is shown as not published.
- **Licences:** Wikipedia (CC BY-SA, attribution), UN (CC BY 3.0 IGO), OWID and UNHCR (CC BY): attribution lines on screen and in the sources list.
- **Stale snapshots:** bundled files carry their year; a yearly refresh script is part of each build script.
- **Unverified sources** (USGS file layout, GOV.UK advice, V-Dem coverage for small states) are checked at the start of their stage and dropped, with a note here, if they fail.

## Decisions needed

1. **Bundle larger datasets into the repo** (OWID energy subset, HDI, USGS minerals, all-years UN migration; a few MB total)? Recommended: yes.
2. **AI "analyst read" on each tab** (premium, cached a week, grounded only in the tab's numbers)? Recommended: yes, as stage 6.
3. **Rankings and trend charts** (rank among 190 countries, 10 to 30 year sparklines on every metric that has a series)? Recommended: yes.
4. **UCDP conflict token** (free, you would request it and add it to Railway)? Recommended: not now; our events plus UNHCR cover current conflict, and UCDP can be added later.
5. **Wikipedia intros** on Government and Geography, with attribution? Recommended: yes.

## Decisions (made by the owner)

All five recommendations accepted: bundle larger datasets; an AI analyst read on each tab (stage 6); rankings and trend charts; no UCDP token for now; Wikipedia intros with attribution.

## Stage 0 as built (foundation)

- **Per-tab endpoint** `GET /api/countries/<cc>/tab/<tab>` (premium, 404 for an unknown tab) backed by `services/country_tabs.py`: one builder per tab, each cached 24 hours, the security tab's event counts added fresh. The older `/detail` endpoint is kept for clients that are still on the old frontend.
- **`services/country_indicators.py`:** World Bank series with year and source, `latest_all` (one call per indicator, shared by every country) for ranks, `stat`/`stats` (value, year, series, rank). Real countries are separated from regions and income groups (217 economies). One retry on a stall, no stand-ins on failure.
- **Frontend:** `CountryDetail.tsx` now only orchestrates; one file per tab in `sidebars/analysis/country/` (Government, People, Migration, Economy, Security, Geography, shared pieces, format helpers). New kit: `Stat` (value, year, rank, change since the first year, trend line), `StatList`, `Sparkline`, pure helpers in `chart.ts` (tested). Only the open tab's data is fetched.
- **People tab** already uses the kit: population and birth rate with rank and trend (Japan: population #12 of 217, birth rate #211 of 217, down 43% since 1990).
- **Note:** a cold country takes several seconds on its first People load (the ranking tables are fetched once, then cached for everyone).
- **Fixed on the way:** if the population series hiccuped while the figures loaded, head counts for religions vanished; the tab now takes population from the same fetch as the figures.

## Stage 1 as built (Economy and People)

- **Bundled data** (`backend/data/country/`, rebuilt by `python scripts/build_country_data.py`, 330 KB): `hdi.json` (UNDP via Our World in Data, 193 countries, 1990 to 2023), `energy.json` (electricity mix, latest year, 214 countries), `minerals.json` (USGS Mineral Commodity Summaries 2025: 116 countries, 76 commodities, with rank among listed producers, share of world output and reserves; critical minerals flagged from USGS's own list). Loaded by `services/country_data.py`.
- **People tab:** 11 World Bank figures with rank and trend (population, life expectancy, birth and fertility rates, growth, urban share, dependency ratio, infant mortality, literacy, secondary enrolment, doctors), the Human Development Index with tier and rank, males and females by age, **language shares** and **largest cities** (new Factbook parsers), religions and ethnic groups as before.
- **Economy tab:** 10 key figures (GDP, GDP per person, growth, inflation, unemployment, government debt, current account, foreign investment, inequality, electricity access) with 35-year series where the World Bank has them, sector shares, **electricity mix**, trade as before, and **critical and strategic minerals** (production, rank among producers, world share, reserves) ahead of other minerals.
- **Trend wording:** percentages and rates move in "points", other figures in percent, and a series that touches zero only says where it started (a percentage change there would mislead).
- **Rank tables** for all 21 indicators are fetched in the background at start-up, so the first visitor's tab is quick.
- Not covered in this stage: government debt and some other World Bank series can be old (the year is always shown); minerals are USGS estimates in the units shown.

## Stage 2 as built (Migration)

- **UN DESA table rebuilt with every year** (1990, 1995, 2000, 2005, 2010, 2015, 2020, 2024): for each country the immigrant trend, the top 15 origins, and the same table read from the other side, the emigrant trend and top 15 destinations (`data_sources/migration_origins.json`, 148 KB, rebuilt by `scripts/build_migration_data.py`). The headline immigrant total is the table's own "all origins" figure (France 9.19M), not the sum of the listed origins.
- **UNHCR** (`data_sources/unhcr.py`, keyless): refugees, asylum seekers, stateless and displaced people living in the country and from the country, by year since 2015, plus where hosted refugees come from and where a country's refugees now live. UNHCR's own country codes are translated from ISO through its countries endpoint (Algeria is ALG, Germany is GFR). The latest year can be a mid-year count.
- **`services/country_migration.py`** builds the tab: share of the population over time (UN counts against the World Bank population), diaspora share, remittances received and sent (World Bank, with rank and trend), net migration, and the Factbook net migration rate.
- **Frontend:** Immigrants, Emigrants, net movement, refugees hosted, people who have fled or are displaced, and money sent home, each with year, trend and source; origin and destination bars from the UN table and UNHCR.
- **Checked on:** France (immigrant share up from 10.1% in 1990 to 13.4%; Algeria, Morocco, Portugal lead), Syria (8.9M emigrants, 36% of its population; 4.9M refugees abroad, mostly Turkey, Germany, Lebanon; 5.5M displaced at home).

## Stage 3 as built (Security)

- **Our events, deeper** (`services/country_detail.build_conflicts`): a 13-week trend of violent, non-statement, non-merged events for the country, the five busiest half-degree areas of the last 30 days with place names (the article-refined name where an event has one, otherwise a reverse lookup of the area's centre through Nominatim, shared with the geocoder's one-request-a-second limit and remembered for a month), and the most severe recent reports. Still media reports, not verified casualty counts.
- **Military** (World Bank, from SIPRI, keyless): spending as % of GDP, in dollars and as a share of government spending, armed forces size, arms imports and exports, each with rank and trend. Some countries' latest year is old (Syria's spending is 2010); the year always shows.
- **Displacement** (UNHCR): refugees from the country and people displaced inside it, with trend.
- **Travel advice** (`data_sources/travel_advice.py`, GOV.UK content API, Open Government Licence): the UK government's warning level for the country with the first lines of its summary and a link. Labelled as one government's advice, not a measure of risk.
- **Alliances and groupings:** the Factbook's international organisation participation, parsed (`parse_memberships`) and grouped (security and arms control, political, economic, other) with full names for about 70 known abbreviations; unknown ones shown exactly as written. This replaces the Wikidata idea: its membership data was incomplete (EU 26 of 27, OECD and others missing), while the Factbook list is complete and consistent. The Government tab can reuse it in stage 4.
- **Checked on:** Syria (travel advice: against all travel; Hama, Golan and Damascus clusters; 4.9M refugees abroad; 5.5M displaced) and Ukraine (military spending 34% of GDP, #1; arms imports #1).

## Stage 4 as built (Government)

- **Factbook government, structured** (the first version read three keys wrongly, so the Legislature, Courts and Parties rows were mostly empty): the legislature with each chamber's seats, electoral system, renewal, term, last and next election, women's share and seats by party (a one-chamber legislature keeps its figures on itself); the courts with how judges are chosen; executive last and next election; citizenship rules; independence, national day and divisions; parties as a list.
- **How democratic** (V-Dem electoral democracy index, bundled in `data/country/democracy.json` from Our World in Data, CC BY): value, rank among 174, trend since 1950 and the political regime (closed or electoral autocracy, electoral or liberal democracy) with the year it began.
- **Office holders** (`data_sources/wikidata.py`, live, remembered a day): previous heads of state and of government with years. The Factbook stays the source for the current ones; Wikidata can lack a current holder's label, so only dated predecessors are shown.
- **Alliances and groupings:** the Factbook list, shared with the Security tab.
- **How power works** (`services/country_power.py`): a short plain-language reading, written by the AI model from the Factbook text only, with the instruction to leave out anything the text does not say; it is remembered for a week and labelled as AI-written. It appears only where an API key is set, so it is untested against the live model (the prompt, the parsing and the empty cases are covered with a fake client).
- **Wikipedia background** (`data_sources/wikipedia.py`): the "Politics of X" intro, with title, link and CC BY-SA 4.0 shown.
- **Dropped:** the IPU Parline parliament data (licensed non-commercial, and this is a paid product); the Factbook's own legislature figures replace it. Key agencies as a Wikidata list (the query timed out and coverage is uneven); the courts, legislature and security services stand in.
- **Licences checked for everything on these tabs:** Factbook (public domain), World Bank, UNHCR, V-Dem and Our World in Data (CC BY), UN DESA and UNDP (CC BY 3.0 IGO), USGS (public domain), GOV.UK (Open Government Licence), Wikidata (CC0), Wikipedia (CC BY-SA, attributed).

## Stage 5 as built (Geography)

- **Free part unchanged** (area, borders from the free profile, the AI narrative). The premium facts follow when the viewer is unlocked.
- **Factbook geography and environment, read out** (`parse_geography`): location and coordinates, area (total, land, water, comparison), land borders with lengths (largest first), coastline and maritime claims, climate, terrain, elevation (highest, lowest, mean), land-use shares (agricultural land and its parts, forest, other), irrigated land, rivers and lakes, natural hazards, population spread, environmental issues, renewable water and water use, carbon dioxide, waste recycled. Shown in the Factbook's own words; only borders and land use are turned into numbers.
- **Figures with rank and trend** (World Bank): land area, population density, forest cover, arable land, renewable fresh water, air pollution (PM2.5), carbon dioxide per person, renewable energy share. (Protected-area share was not available.)
- **Hazards active now:** GDACS events (cyclones, floods, wildfires, droughts) the Weather mode already reads, matched to the country by name, most serious alert first, each with its report link. An empty list is shown as no active hazards; an unreachable feed leaves the group out.
- **Wikipedia "Geography of X" background** with title, link and CC BY-SA 4.0 shown (same attribution machinery as Government).
- **Free profile fix:** a single stalled World Bank call used to leave the free "Area" showing "unavailable" for six hours; it now retries through the indicator helper.
- **Process finding:** the frontend's `npx tsc --noEmit` at the project root checks nothing (the root tsconfig only has references); the real check is `npx tsc -b` or `npx tsc -p tsconfig.app.json --noEmit`. Re-run on everything built so far: two type errors in `Security.tsx` (fixed), nothing else.
