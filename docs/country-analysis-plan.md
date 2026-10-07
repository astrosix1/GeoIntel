# Country analysis revision

Plan for the four groups the owner asked for. Nothing here is built yet.

## What was verified (live, keyless)

| Source | Gives | Notes |
|---|---|---|
| CIA World Factbook JSON mirror (`factbook/factbook.json` on GitHub, updated Sep 2026) | Government type, constitution, executive/legislative/judicial branches, parties; religions and ethnic groups with percentages; age structure with percentages and counts; birth rate; net migration; export/import commodities and partners; natural resources; ports, airports, railways; refugees/IDPs; terrorist groups | Public domain. Each field is dated (e.g. "2025 est."). Free text with HTML entities, so it needs a careful parser. |
| World Bank indicators | Birth rate (`SP.DYN.CBRT.IN`), age shares (`SP.POP.0014/1564/65UP.TO.ZS`), migrant stock (`SM.POP.TOTL`), net migration (`SM.POP.NETM`) | Already used in the app. Numeric, dated. |
| Wikidata SPARQL | Current head of state / government (open-ended statements) | Works; labels need the right service call. Useful as a cross-check on the Factbook leader. |

## Not available keylessly (be honest about it)

- **Where immigrants come from, with counts.** Totals are available (migrant stock). Origin-by-country counts need the UN DESA bilateral table (a downloadable file, not an API). Factbook only lists a few "major source countries" for some states, in free text.
- **Current conflicts.** No keyless live feed. Options: summarise the app's own recent events for that country (counts by type, last 30 days, linked to the map), plus the Factbook "Terrorism" and "Transnational issues" text. ACLED/UCDP would need keys.
- **Rare minerals.** Factbook "Natural resources" lists them as text; no tonnage or reserves. Show the list, flag it as a resource list, not production.

## Decisions needed from the owner

1. **Immigration origins:** (a) ship the totals plus Factbook's listed source countries and say "full breakdown unavailable"; or (b) bundle the UN DESA bilateral table as a static file refreshed yearly (accurate counts, one-off import script, ~a few MB). Recommended: (b).
2. **Conflicts:** use our own events table (recommended) or add a keyed ACLED/UCDP source.
3. **Free or premium:** recommended: facts free, AI narrative stays as is.

## Design

- New `data_sources/factbook.py`: ISO alpha-2 to Factbook folder/GEC code map, fetch with 24h cache, parsers for religions, ethnic groups, age structure, rates, commodity lists. Parsers return `None` for anything they cannot read cleanly.
- `services/country_profile.py` gets new sections: `government`, `demographics` (extended), `migration`, `economy` (commodities, resources, infrastructure), `conflicts`. Each carries `source` and `as_of`. Missing data gives an honest "unavailable".
- `CountryAnalysis.tsx` tabs: Government, People, Migration, Economy and infrastructure, Security. Uses the `Section` / `KeyValue` kit.
- AI narrative stays grounded: it receives only these facts.

## Stages

1. Factbook connector, parsers, tests (fixtures from real files for several countries incl. odd ones).
2. Government, People (religions, ethnicities, age groups, birth rate) sections, backend plus UI.
3. Migration (per decision 1) and Economy and infrastructure.
4. Security/conflicts from own events, polish, accessibility, tests.

## Risks

- Factbook free text varies by country; unparsed fields fall back to the raw text, shown as-is.
- Factbook is a snapshot (leaders can lag); show "as of" and cross-check with Wikidata.
- Country code mapping for small territories.
