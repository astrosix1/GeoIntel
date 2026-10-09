# Cascade simulator: from a toy into a working product

Plan for rebuilding the cascade simulator. Nothing here is built yet.

## Where it stands

- **It no longer exists in the app.** The first version (`analyze_cascade` and `/api/crises/<id>/cascade`) was dropped when the app was rebuilt. Only its leftovers remain: the `actors` and `relationships` tables, their seed data, and a few README lines.
- **What it did was not trustworthy.** It walked a hand-made graph two steps out from a crisis's actors and multiplied hand-set weights ("alliance x 0.7, economic x 0.4") into a "probability". Those numbers had no source, and the rest of the app's rule is that nothing is a made-up number (the scenarios feature refuses percentages outright).
- **The data behind it is thin.** 68 actors (many without military power, which has no real source anywhere), and 81 hand-written relationships: 46 alliances, 16 conflicts, 11 tensions, 8 economic. It covers ~68 countries and blocs, not the ~190 the rest of the app knows.

## What the app has now that the old one did not

Real, sourced data that can carry a cascade, all already in the code or bundled:

| Layer | Source we already have | What it gives a cascade |
|---|---|---|
| Trade dependence | CIA World Factbook: top export and import partners with shares, main commodities | "X takes 30% of Y's exports" is a real edge, for almost every country |
| Energy | Bundled OWID energy mix, Factbook energy | How exposed a country is to oil, gas, coal; who it buys from |
| Critical minerals | Bundled USGS production and reserves | Supply-chain edges for chips, batteries, metals |
| People and displacement | UN migrant stock (all origins and destinations), UNHCR refugees and IDPs | Where displaced people would go; existing diaspora ties |
| Alliances and blocs | Wikidata memberships (UN, NATO, EU, BRICS, OPEC, G20...), Factbook | Treaty and bloc ties that can be checked, not just asserted |
| Military and economy weight | World Bank (military spend % GDP, armed forces, GDP) | Relative size, not invented scores |
| Live conflict context | Our own events, situations and the country pattern | Where the trigger is happening now; what is already burning nearby |
| Hazards | Live GDACS feed | Natural-hazard triggers (cyclone hits a port, flood hits a producer) |

## What "a working product" should mean

A user picks a **trigger**, and sees **who is exposed, through which link, with what evidence**. Not a forecast.

- **Triggers:** a current event or situation (one click from its analysis), or a hypothetical built from a short list of templates: a country invaded or attacked; a sanction or embargo on a country or product; a chokepoint closing (Hormuz, Suez, Malacca, Taiwan Strait, Bosphorus); an export ban on a commodity or mineral; a major hazard hitting a key producer or port; a government collapse.
- **Engine:** a transparent, rule-based propagation over a graph built from the real layers above. Every edge carries its evidence ("China takes 31% of Australia's exports, Factbook 2023"), every hop is one of a small set of named mechanisms, and nothing is multiplied by an unexplained constant. Exposure comes out as **High, Moderate or Low** from stated thresholds (for example a share of exports above 20% is High), never a percentage chance.
- **Time horizon:** each effect is placed in days, weeks or months by its mechanism (a shipping chokepoint bites in days, a mineral shortage in months), with the reasoning shown.
- **Output:** (1) a map with affected countries coloured by exposure, (2) a ranked list, each entry opening a "why" panel that shows the chain of links and the numbers and sources behind it, (3) a plain "what would change this" list (alternatives, stockpiles, other suppliers where the data shows them), (4) a clear "not modelled" note (markets, politics, decisions of leaders).
- **Optional AI narrative (premium, needs a key):** one grounded paragraph written only from the computed result, like the country analyst read. It cannot add an effect the engine did not find.
- **Keep and compare:** premium users can save a scenario, name it, reopen it, and compare two side by side.
- **No key needed** for the engine and the map. The narrative is the only part that needs the model.

## Where it lives in the app

- A new **Cascade** panel in the analysis sidebar for events and situations ("Run a cascade from this"), and a **Scenarios workspace** reached from the top bar for hypothetical triggers. The old "possible scenarios" section on events stays hidden until the owner decides how the two relate.
- Premium, as the country tabs and scenarios are. A short free preview (the first hop of a current event) is an option for the decisions list.

## How it is built

- **Graph builder** (`services/cascade_graph.py`): builds the country graph from the layers above, once a day, cached. Nodes are countries (ISO code) plus the few blocs that matter; edges are typed (trade, energy, mineral, migration, treaty, bloc) with their value, year and source. The 68-actor hand table is replaced by this, with the old curated alliance and conflict edges kept only where a source checks them.
- **Engine** (`services/cascade_engine.py`): pure functions. Input: trigger and options. Output: a tree of effects with exposure, mechanism, horizon, evidence and caveats. Deterministic and unit-tested row by row, like the severity table.
- **Triggers** (`services/cascade_triggers.py`): each template is a small description of what it removes or blocks (a country's exports, a chokepoint's flow, a commodity), so adding one is data, not code.
- **API:** `POST /api/cascade/run` (trigger in, result out; rate-limited, premium), saved scenarios in a new Supabase table `geointel_cascades` (SQL file `008_...`), `GET` to list and open them.
- **Frontend:** the panel, a trigger picker, the result map layer (reusing the country polygon layer), the evidence panel, the compare view.
- **Tests:** engine rules with fixture graphs, graph builder against recorded source samples, trigger templates, the API (premium, limits), and the frontend rendering.

## Stages

0. **Graph and engine core:** the graph builder over the real layers and the engine for two mechanisms (trade dependence and energy), with tests and a command-line way to run it. No interface yet; checked against five well-known cases (an embargo on Russian gas, Hormuz closing, a Taiwan chip disruption, a Ukraine grain halt, a Red Sea closure) to see whether the output is sensible.
1. **Triggers and the panel:** the six trigger types, the Cascade panel on events and situations, the result list with evidence.
2. **Map and horizons:** the exposure map layer, days/weeks/months, "what would change this".
3. **More mechanisms:** critical minerals, displacement and migration ties, treaty and bloc links.
4. **Save, reopen, compare** (premium) and the AI narrative.
5. **Hardening:** limits, caching, mobile, accessibility, a methods page that explains every rule and threshold in plain words.

Each stage ends with tests, a browser check and the usual "commit and continue".

## Risks

- **Credibility.** A simulator invites people to read it as a prediction. The design answers this with named mechanisms, shown evidence, qualitative exposure only and an explicit "not modelled" list; a methods page states the limits.
- **Data gaps.** Factbook partner shares are a few years old and some countries have none. Gaps show as "not published" and the country is left out of that mechanism, never guessed.
- **Chokepoints and sanctions are not in any open dataset** as clean tables. They would be a small hand-curated table (route, share of world flow, who depends on it), sourced and dated, and shown as such. This is the weakest data in the plan.
- **Sanctions and treaties change.** The curated parts need a "last reviewed" date and an owner to refresh them.
- **Scope creep.** The temptation is to add markets, prices and politics. The plan stops at structural exposure.

## Decisions needed

1. **Meaning:** are you after "who is exposed to this trigger, with evidence" (as above), or something closer to a game-like what-if with scores? Recommended: the evidence-based exposure view.
2. **Triggers:** is the list of six right, and should current events be the main entry point with hypotheticals second, or the other way round?
3. **Numbers:** agree to High, Moderate and Low with stated thresholds and no percentage chances?
4. **Curated tables:** are you happy to hand-curate and date a small table of chokepoints and major sanctions regimes, with a "last reviewed" note?
5. **Access:** all premium, or a free first-hop preview on current events?
6. **Scenarios section:** keep the hidden "possible scenarios" on events separate for now, or fold it into this workspace later?

## Decisions (answered 2026-10-09)

1. Both: evidence-based exposure from a current event or situation, and a what-if workspace with templates.
2. The six triggers are right.
3. High, Moderate and Low with stated thresholds; no percentage chances.
4. A small hand-curated, dated table of chokepoints and sanctions is fine.
5. All premium.
6. The hidden "possible scenarios" on events stays separate.

## Stage 0 finding (the sanity check did its job)

The first engine uses Factbook trade partners, which publish only each country's **top five partners for all goods**. Run on real data:

- An embargo on Russian gas lists Armenia, Georgia, Turkey, Bulgaria, Tunisia and India sensibly, but misses Hungary, Slovakia and Austria, which are not in anyone's published top five.
- A Ukraine grain halt lists only Moldova. The real exposure (Egypt, Lebanon, Tunisia and others buying Ukrainian wheat) is invisible, because grain is a small part of those countries' total imports.
- A Qatar gas cut lists only Pakistan and Oman.

So the Factbook alone is too coarse for commodity cases. **UN Comtrade's public preview API works without a key** and returns bilateral trade by commodity: Egypt's 2022 cereal imports, for example, show Russia $2.2 billion, Brazil $1.6 billion, Ukraine $0.8 billion of $7.4 billion. A build script can bundle shares for the commodity groups the triggers need (fuels, gas, cereals, selected metals) into `backend/data/cascade/`, the same pattern as the other bundled datasets. This is the recommended next step before the interface.
