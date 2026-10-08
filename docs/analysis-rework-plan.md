# Event Analysis tab: more informative

Plan for reworking the **Analysis** tab of the event panel (the tab you see when you click a pin or an event). Nothing here is built yet. Hazard and country panels are out of scope unless you say otherwise.

## What the tab shows today

Photo or video link, "Nearby hazard" (when a hazard is in range), then **one AI briefing paragraph** with numbered citations, then the premium **Scenarios** block. The "why" and the sources have just moved to More Info. For many events there is no model (no key, or a thin story) and the briefing falls back to a static two-line summary: the headline, "Global Severity: 53/100", and a trend sentence.

So the tab answers "what is this?" in a paragraph, but not: *how bad, how new, who is involved, what is the pattern here, what is the country context, what is not known.*

## What the backend already has, and how good it is

Checked on a real merged event ("UN human rights chief … Christa Pike's botched execution", two outlets):

| Piece | Exists in the API | Used in the UI | Quality |
|---|---|---|---|
| AI briefing with numbered citations | yes | yes | good with a model; a thin static fallback without one |
| Extracted facts (killed, injured, place, scale cues, one-line summary) | yes (`crises.facts`, needs the model key) | only through the severity reasons | good where present |
| Escalation trend (`/escalation`) | yes | **no** | **misleading now**: it reads stored severity snapshots, and older snapshots are on the old scale (90) while new ones are on the strict scale (53), so this event reads "de-escalating, down 37" purely because of the rescoring |
| Economic impact (`/economic`) | yes | no | **not usable**: "sectors typically exposed: Defense, Shipping, Energy" for a US legal story, from a fixed table by event type |
| Source reliability (`/reliability`) | yes | no | a default score of 65 and "unverified" for unlisted outlets; thin |
| Deep history (`/history`) | yes | no | "No history available." (static) |
| Related events (`/related`) | yes | no | usable: same country and type nearby in time |
| Country profile, country tabs (travel advice, 90-day violence trend, leaders) | yes | not linked from the event | good, and grounded |

Two of these should be **dropped or replaced**, not shown: the economic exposure table and the snapshot-based escalation.

## Proposed layout (top to bottom)

1. **At a glance** (a strip): kind (something that happened, or a statement), severity level and number, "first reported 3 h ago", source count, place and how precise the pin is. Mostly already in the badges; it becomes one readable row with the meaning spelled out.
2. **What we know** (the briefing, restructured): a two-sentence summary, then 3 to 5 **key points**, each with its citation numbers. Same model call and same grounding rule as today, with structured output instead of one paragraph.
3. **What is not known** (same call): up to three things the sources do not say or disagree on ("no casualty figure given", "sources differ on the location"). This is the part that makes it analysis rather than a summary.
4. **Facts from the reporting** (chips, only when extracted): killed, injured, named place, scale cues, each labelled "stated in the article".
5. **The pattern here:** how many violent reports in this country in the last 7 days against the 7 before, a small weekly trend, and the other recent events nearby of the same type (from the existing related-events data). Replaces the old escalation block with something real: a trend of *reports in the area*, not of one event's stored score.
6. **Country context** (a compact card): population, head of government, travel advice level, the country's 90-day violence trend, and a button that opens the country analysis. Free: population and capital. Premium: travel advice, trend and leaders (they are premium tabs already).
7. **Parties:** the actors the event involves, as chips, where the data has them (`stakeholders`), each opening the matching country.
8. **Scenarios** (premium, unchanged) at the foot.

Everything states its source and age. A block with nothing real to show is left out, not filled.

## How it gets built

- **Backend:** `services/event_analysis.py` assembles the new blocks into one `GET /api/crises/<id>/analysis` response (pattern counts, related events, country context, parties). The briefing call in `services/briefing.py` returns the structured fields (summary, key points with citations, unknowns); the old paragraph stays as the fallback text. Cached with the story's own stamp so a new merged source refreshes it, as the briefing does now.
- **Frontend:** the Analysis tab renders the blocks as small, collapsible sections using the existing section and stat components; a block is hidden when its data is absent. Country context links use the existing country selection.
- **Grounding rules unchanged:** the model sees only the story's sources, extracted facts and the numbers above; key points must cite; unknowns are phrased as "not reported", never as guesses.
- **Cost:** no extra model call (the structured output replaces the paragraph in the call that already runs, cached per story).

## Stages

1. **Foundation and the pattern block:** `/analysis` endpoint with the pattern, related events and country context; the at-a-glance strip; remove the broken escalation use. Tests with fixtures.
2. **Structured briefing:** key points, unknowns, parties, facts chips; fallback when there is no model.
3. **Country context card and polish:** links into the country analysis, mobile layout, loading and empty states, accessibility.

Each stage ends with tests, a browser check on three very different events (a physical event with casualties, a statement, a thin one-source story) and the usual commit.

## Risks

- **Thin stories** (one outlet, no extracted facts) will show fewer blocks; that is correct but should not look broken.
- **Briefing format change** touches a cached, shared structure; old cached briefings are read as before until they expire.
- **Pattern counts depend on the topic filter** (violent types, non-statement); the labels say exactly what is counted.
- **The model key**: key points and unknowns need it. Without one, the tab shows the at-a-glance strip, facts, pattern and country context, which are all data, and the static summary.

## Decisions needed

1. **Scope:** only the event Analysis tab (as above), or also the hazard and country analysis panels?
2. **Free or premium:** key points and the pattern free, country context and parties premium? (That matches how the country tabs are split.)
3. **Replace the old escalation and economic blocks** with the pattern block and drop the economic table, as proposed?
4. **Unknowns:** show "what is not known" on every event that has a briefing? Recommended: yes.
