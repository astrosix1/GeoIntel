#!/usr/bin/env python3
"""
Clean up crises stored BEFORE the event pipeline existed.

New syncs go through event_pipeline/ (relevance, locations, titles, dedup);
rows already in the database never did. This script runs every active row
through the parts of the pipeline that work on stored fields, and:

  - deactivates legacy GDELT rows (no raw fields survive to re-check them,
    and GDELT only covers the last hour anyway — current events come back
    through the pipeline on the next sync; --keep-legacy-gdelt to skip);
  - deactivates news rows that fail the outlet/topic/actor checks;
  - normalizes the country, checks coordinates are inside it (or fixes the
    country from the coordinates), and backfills country_code,
    location_precision, last_seen_at, source_count and crisis_sources;
  - cleans titles, deactivating rows with no usable title (ACLED rows whose
    title was an ID code come back with a real title on the next sync);
  - merges duplicate rows of the same event: the best one stays, the rest
    are deactivated and recorded as its sources.

Nothing is ever deleted — deactivated rows keep their severity snapshots
and forecasts, and a later sync that reports them again revives them.
Curated, sample, manual, upcoming and human-verified rows are only
backfilled, never deactivated or merged.

    cd backend
    python scripts/reprocess_crises.py            # dry run: prints the plan
    python scripts/reprocess_crises.py --apply    # writes it

Run `alembic upgrade head` first (the new columns must exist).
"""
import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_args():
    parser = argparse.ArgumentParser(description='Reprocess stored crises through the event pipeline.')
    parser.add_argument('--apply', action='store_true', help='write changes (default: dry run)')
    parser.add_argument('--keep-legacy-gdelt', action='store_true',
                        help="don't deactivate GDELT rows stored before the pipeline")
    parser.add_argument('--samples', type=int, default=5, help='example titles to print per action')
    return parser.parse_args()


def main():
    args = parse_args()
    sys.path.insert(0, BACKEND_DIR)
    os.chdir(BACKEND_DIR)
    from dotenv import load_dotenv
    load_dotenv()

    from models import Session, Crisis, CrisisSource
    from event_pipeline.config import get_config
    from event_pipeline.normalize import normalize_candidate, canonical_url
    from event_pipeline.relevance import check_news
    from event_pipeline.location import check_location
    from event_pipeline.titles import clean_title
    from event_pipeline import dedup

    exempt_sources = set(get_config().get('lifecycle', {}).get('exempt_sources', []))
    now = datetime.utcnow()
    actions = Counter()
    samples = defaultdict(list)

    def note(action, row):
        actions[action] += 1
        if len(samples[action]) < args.samples:
            samples[action].append(f"[{row.source}] {row.title}"[:110])

    def deactivate(row, reason):
        row.is_active = False
        note(f"deactivate: {reason}", row)

    session = Session()
    try:
        rows = session.query(Crisis).filter(Crisis.is_active == True).all()  # noqa: E712
        print(f"{len(rows)} active crises")
        survivors = []

        for row in rows:
            exempt = (row.source in exempt_sources or row.status == 'upcoming' or row.is_verified)
            source = row.source or ''

            if source == 'GDELT' and row.last_seen_at is None and not args.keep_legacy_gdelt and not exempt:
                deactivate(row, 'legacy_unfiltered_gdelt')
                continue

            url = row.source_url or (row.source_id if (row.source_id or '').startswith('http') else None)
            is_news = source == 'NewsAPI' or source.startswith('NEWS_API')
            if is_news and not exempt:
                meta = {'kind': 'news', 'url': url, 'text': f"{row.title} {row.analysis or ''}"}
                reason = check_news({'stakeholders': row.stakeholders or ''}, meta)
                if reason:
                    deactivate(row, reason)
                    continue

            candidate = {'id': row.id, 'type': row.type, 'title': row.title, 'country': row.country,
                         'latitude': row.latitude, 'longitude': row.longitude,
                         'date_start': row.date_start}
            reason = normalize_candidate(candidate)
            meta = {'precision': row.location_precision or ('country' if (row.location_confidence or 70) < 60
                                                             else 'city')}
            if not reason:
                reason = check_location(candidate, meta)
            if reason:
                if exempt:
                    note('kept exempt despite: ' + reason, row)
                    survivors.append((row, None))
                    continue
                deactivate(row, reason)
                continue

            if candidate['country'] != row.country or row.country_code != meta['country_code']:
                note('country normalized/backfilled', row)
            row.country = candidate['country']
            row.country_code = meta['country_code']
            row.location_precision = row.location_precision or meta['location_precision']
            if (candidate['latitude'], candidate['longitude']) != (row.latitude, row.longitude):
                row.latitude, row.longitude = candidate['latitude'], candidate['longitude']
                note('moved to country centroid', row)

            if not exempt:
                title = clean_title(row.title, url=url)
                if not title:
                    deactivate(row, 'no_usable_title')
                    continue
                if title != row.title:
                    note('title cleaned', row)
                    row.title = title

            if url and not row.source_url:
                row.source_url = url
            row.last_seen_at = row.last_seen_at or row.date_updated or row.date_start or now
            survivors.append((row, url))

        # Merge duplicates among the survivors (exempt rows never merge away).
        mergeable = [(r, u) for r, u in survivors
                     if not (r.source in exempt_sources or r.status == 'upcoming' or r.is_verified)]
        by_block = defaultdict(list)
        for row, url in mergeable:
            by_block[row.country_code].append((row, url))
        precision_rank = {'point': 4, 'city': 3, 'region': 2, 'country': 1}
        merged_into = {}
        for block in by_block.values():
            block.sort(key=lambda ru: (dedup.source_priority(ru[0].source),
                                       precision_rank.get(ru[0].location_precision, 0),
                                       len(ru[0].title or '')), reverse=True)
            primaries = []
            for row, url in block:
                view = dedup.view_from_row(row)
                home = next((p for p in primaries if dedup.is_match(p[1], view)), None)
                if home is None:
                    primaries.append((row, view))
                else:
                    merged_into[row.id] = home[0]
                    row.is_active = False
                    note('merged into another row (deactivated)', row)

        # Provenance + source_count for every surviving row.
        members = defaultdict(list)
        for row, url in survivors:
            primary = merged_into.get(row.id, row)
            members[primary.id].append((row, url))
        for row, _ in survivors:
            if row.id in merged_into:
                continue
            known = {k for (k,) in session.query(CrisisSource.url_key).filter(CrisisSource.crisis_id == row.id)}
            for member, url in members[row.id]:
                key = (canonical_url(url) if url else f"{member.source}:{member.source_id or member.id}")[:500]
                if key not in known:
                    known.add(key)
                    session.add(CrisisSource(crisis_id=row.id, source=member.source,
                                             external_id=(member.source_id or member.id)[:100],
                                             url_key=key, url=url, title=(member.title or '')[:300],
                                             published_at=member.date_start))
            row.source_count = max(len(known), 1)

        print("\nPlan:" if not args.apply else "\nApplied:")
        for action, count in actions.most_common():
            print(f"  {count:5d}  {action}")
            for example in samples[action]:
                print(f"           - {example}")
        remaining = sum(1 for r, _ in survivors if r.id not in merged_into)
        print(f"\n{remaining} crises remain active (from {len(rows)})")

        if args.apply:
            session.commit()
            print("Committed.")
        else:
            session.rollback()
            print("Dry run — nothing written. Re-run with --apply to write.")
    finally:
        session.close()


if __name__ == '__main__':
    main()
