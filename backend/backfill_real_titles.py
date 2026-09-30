"""
One-time backfill pass against the LIVE database, resolving real article
headlines for existing GDELT crisis rows that still carry a generic
auto-generated title.

Phase 11 (see the plan file) added real title resolution — replacing a
GDELT row's CAMEO-verb-constructed title (e.g. "Seoul criticizes Ukraine")
or blank-actor fallback ("Conflict-related event in {country}") with the
real article headline from its own source_url — but only for NEWLY
ingested rows, at sync time. It was explicitly scoped that way and never
touched the rows already in the database before it shipped. This script
is the retroactive counterpart, reusing the exact same
GDELTConnector._resolve_real_titles() function ingestion uses (bounded-
concurrency HTTP fetches, honest fallback on any failure — never blanks
or fabricates a title) run against the current DB instead of a fresh sync
batch.

Confirmed live before this script existed: 7,447 of 8,295 GDELT rows in
the live DB still carried a generic title.

Usage:
    python backfill_real_titles.py            # dry run, reports what WOULD change
    python backfill_real_titles.py --apply     # backs up geointel.db, then fetches + updates

Only touches source='GDELT' rows. Real network calls happen even in dry-run
mode (title resolution has to actually fetch each page to know what it
would become) — only the DB write is gated behind --apply.
"""
import argparse
import shutil
import sys
from datetime import datetime

from models import Crisis, Session, engine
from data_sources.gdelt import GDELTConnector

GENERIC_VERBS = (
    ' fights ', ' criticizes ', ' pressures ', ' rejects ', ' attacks ',
    ' threatens ', ' demands action from ', ' protests against ',
    ' reduces relations with ', ' shows military force near ',
    ' uses mass violence against ',
)


def _looks_generic(title):
    if not title:
        return False
    if title.startswith('Conflict-related event in'):
        return True
    if ' — conflict event in ' in title or ' — conflict-related event in ' in title:
        return True
    return any(v in title for v in GENERIC_VERBS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Actually update rows (default: dry run)')
    parser.add_argument('--limit', type=int, default=None, help='Only process the first N generic-titled rows (for testing)')
    args = parser.parse_args()

    session = Session()
    try:
        gdelt_crises = session.query(Crisis).filter(Crisis.source == 'GDELT').all()
        generic = [c for c in gdelt_crises if _looks_generic(c.title)]
        if args.limit:
            generic = generic[:args.limit]

        print(f"Loaded {len(gdelt_crises)} GDELT-sourced crises, {len(generic)} with a generic title to resolve.")
        if not generic:
            print("Nothing to backfill.")
            return

        # Bumped from the sync path's default 8 — this is a one-time bulk
        # job spread across thousands of distinct external domains (not a
        # recurring hourly cost), so more concurrency is safe here without
        # meaningfully increasing load on any single real site.
        GDELTConnector._TITLE_RESOLUTION_WORKERS = 20

        as_dicts = [{'id': c.id, 'title': c.title, 'source_url': c.source_url} for c in generic]
        print(f"Resolving real titles for {len(as_dicts)} rows (real network calls, bounded concurrency)...")
        start = datetime.utcnow()
        resolved = GDELTConnector._resolve_real_titles(as_dicts)
        elapsed = (datetime.utcnow() - start).total_seconds()
        print(f"Done in {elapsed:.1f}s.")

        by_id = {c.id: c for c in generic}
        changed = [r for r in resolved if r['title'] != by_id[r['id']].title]
        print(f"Real titles found for {len(changed)}/{len(as_dicts)} rows; "
              f"{len(as_dicts) - len(changed)} kept their honest generic fallback (fetch failed or no usable title).")

        if not changed:
            print("No rows to update.")
            return

        if not args.apply:
            print("\nDry run only — pass --apply to actually write these changes.")
            print("Sample of rows that would change (first 10):")
            for r in changed[:10]:
                print(f"  {r['id']}\n    old: {by_id[r['id']].title[:80]}\n    new: {r['title'][:80]}")
            return

        backup_path = f"geointel.db.bak-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        db_path = engine.url.database
        if db_path:
            shutil.copy2(db_path, backup_path)
            print(f"Backed up {db_path} -> {backup_path}")
        else:
            print("WARNING: could not resolve a sqlite file path to back up — proceeding without a backup.")

        for r in changed:
            by_id[r['id']].title = r['title']
        session.commit()
        print(f"Updated {len(changed)} crisis rows with real headlines.")
    finally:
        session.close()


if __name__ == '__main__':
    sys.exit(main())
