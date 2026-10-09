# Fewer pins, bigger analysis: one article one pin, then situations

Plan for cutting duplicate pins and building one analysis from many articles about the same thing. Nothing here is built yet. It extends the story merging already in `services/stories.py`.

## Why

From the dev data, last 48 hours:

- 9,435 active events, but only about 5,800 distinct headlines and about 5,790 distinct article URLs.
- About 1,090 headlines appear under more than one country. One article is tagged with a country for every place it mentions, so it becomes several pins ("American Ignorance Risks Fueling Deadly Middle East Sectarianism" sits under 8 countries).
- Junk titles become pins: "Facebook" (17), "newsroomamerica.com" (16), "Conflict-related event in India" (21).
- Beyond exact duplicates, different articles about one developing story (the Houthi attacks on Saudi airports this week) each get their own pin and their own near-identical analysis.

The current merge rules need the **same country**, and compare only pairs, so neither problem is caught.

## Two layers

**Layer 1: one article, one pin.** Free, no key. Merges the same article whatever country it was tagged with, and filters junk titles.

**Layer 2: situations.** Groups different articles about the same developing story into one *situation* with one combined analysis. The grouping is code only. The prose analysis is optional and uses the model when a key exists; without one the situation still gets a structured, extractive summary.

## Layer 1 in detail

- **Merge across countries.** Same normalised URL, or the same normalised headline, merges regardless of country. The primary is the event whose country is best supported: the country named in the headline or extracted `facts.country` first, then highest location confidence, then earliest. The other countries stay recorded on the story as "also tagged" so nothing is lost.
- **Junk filter.** A title that is only a domain or a site name ("Facebook", "newsroomamerica.com") or a bare template ("Conflict-related event in India") is not shown as a pin. It is kept in the database but flagged `is_active = false`, with the reason recorded, so it is reversible. The template check reuses `is_generated_title`, which already exists.
- **Where it runs.** At ingest in `data_sources/gdelt.py` (before the upsert) and in `merge_recent`, which already re-checks the last 3 days. A one-off, idempotent backfill covers the last 7 days.
- **No schema change needed** beyond an `also_tagged` JSON text column on `crises`.
- **Expected effect:** roughly 35 to 40% fewer pins on the dev numbers, to be rechecked after the backfill.

## Layer 2 in detail

### Grouping (code only, no key)

- **Similarity between stories** combines: shared significant words weighted by rarity (TF-IDF over the last 3 days of headlines), shared named entities (capitalised names in headlines and excerpts), shared actor codes, distance (same country or within about 300 km) and time (within 3 days).
- **Clusters** form by linking stories whose combined score passes a strict threshold, then taking connected groups, with a size cap and a rule that a cluster must have one dominant theme (so one popular name does not pull in everything).
- **Borderline pairs** stay separate without a key. With a key, the existing cheap yes/no check (`story_merge_checks`, capped per run) decides them, as in stage 1 of the story pipeline.
- **Storage:** a `situations` table (id, title, country, centre, first/last report, story count, outlet count, stamp) and `crises.situation_id`. The situation's id reuses its earliest story's id so saved items, comments and alerts keep working.
- **Reversible:** stories are never deleted or merged destructively; a situation is a grouping on top.

### The analysis, two modes

**Keyless (extractive), always available.** A situation page shows only things drawn from real data:

- A **timeline** of every story in order, with outlet, time and link.
- **Scale**: story and outlet counts, first and last report, and the existing country pattern block.
- **Main headline** (the most widely reported) and the **different angles** (headlines that differ most).
- **Key sentences**: the sentences from stored article excerpts that the most outlets repeat, shown quoted and attributed. Scored by shared key terms; no text is generated.
- **Stated figures**: deaths and injuries only where an excerpt states them explicitly ("5 killed"), shown as "stated in the headline or excerpt" and never summed or estimated.

**With a key (premium, as today).** One model call per situation, cached against the situation's stamp, using all its sources: the structured briefing already built (summary, cited key points, what is not known), now over every story. Where outlets disagree, the model says so. No extra call per story.

### Showing it

- One **pin per situation**, labelled "N stories". The popup and the panel's analysis tab show the situation; a "Stories in this situation" list opens each original event.
- A situation with one story looks exactly as today.
- Lists, filters and counts use situations, so "7,637 events" falls accordingly. The label stays "events" unless you prefer "situations".

## Stages

1. **Layer 1:** cross-country merge, junk filter, `also_tagged`, backfill; tests with fixtures from the real duplicate cases (the 8-country article, the Houthi pair, the Paris tear-gas pair, the USS Lincoln trio).
2. **Grouping:** TF-IDF and entity similarity, clustering, `situations` table and migration, `merge_recent` extension; tests for threshold, size cap, one-theme rule.
3. **Keyless situation view:** timeline, angles, key sentences, stated figures, the stories list; endpoint and panel.
4. **Model mode:** the structured briefing over a situation's sources; cache by stamp; borderline-pair check when a key exists.
5. **Pins and lists:** one pin per situation, counts, mobile layout, accessibility.

Each stage ends with tests, a before-and-after on the dev data (pins, distinct situations) and a browser check, and waits for your "commit and continue".

## Risks

- **Over-merging.** A situation that is too broad is worse than duplicates. Thresholds are strict by default, the stories are always listable, and the size cap and one-theme rule limit damage. I would tune against 30 hand-checked real groups before enabling it.
- **Wrong country on the primary.** A cross-country merge picks one pin. The "also tagged" list and the headline-country rule reduce this, but some will be arguable.
- **Extractive sentences read choppily.** They are quoted and attributed, never rewritten, and the model mode replaces them where a key exists.
- **Ids and saved items.** Keeping the earliest story's id for the situation avoids breaking comments, saves and alerts, as the story merge does.
- **Sparse dev history.** The dev database only covers recent days, so tuning on it favours short windows; production history may behave differently.

## Decisions needed

1. **Order:** build Layer 1 first and stop to look at the result, or continue straight on to situations? Recommended: Layer 1 first.
2. **Junk filter:** hide junk-titled events entirely (recommended, reversible), or keep them as pins marked "low quality"?
3. **Wording:** call the grouped pins "situations" in the interface, or keep "events" with "N stories"? Recommended: "events", with "N stories".
4. **Keyless view:** is showing quoted key sentences from articles acceptable, or should the no-key view carry only the timeline and counts? Recommended: include the sentences, short and attributed.
