"""
One-time cleanup pass against the LIVE database, consolidating the
near-duplicate GDELT crisis rows that predate the fan-out-cap fixes in
data_sources.py (GDELT_MAX_CRISES_PER_SOURCE_URL lowered 6->2,
GDELT_MAX_CRISES_PER_EVENT_CLUSTER and, since Phase 22, a per-(title,day)
syndication cap added) AND the content-quality filters added alongside
them (self-referential actor pairs, generic-actor-name titles, and
blank-actor rows coded under a violent CAMEO root). All of these only
apply to NEW rows at ingestion time — they don't touch what's already in
the database, which is exactly why the first run of this script (Phase 21,
geographic dedup only) didn't fully fix what users were still seeing:
it never re-validated existing rows against filters added in the same
phase, let alone the ones added later in Phase 22.

Confirmed live before this script existed: one real event (a UN General
Assembly speech) had 574 crisis rows across 217 source URLs; 202 separate
rows shared the exact same Washington DC coordinate on one day. Confirmed
live in Phase 22: 941 self-referential-title rows and 57 generic-actor-
leading-title rows survived the Phase 21 cleanup untouched; ~397 blank-
actor rows under violent CAMEO roots (366 root-19 FIGHT, 31 root-18
ASSAULT) account for most of the still-unchanged severity-90-100 share.

Reuses the exact same GDELTConnector cap/detection functions ingestion
uses, run against the current DB instead of a fresh sync batch, so "which
rows survive" is defined in exactly one place.

Usage:
    python cleanup_duplicate_crises.py            # dry run, prints what WOULD be deleted
    python cleanup_duplicate_crises.py --apply     # backs up geointel.db, then actually deletes

Only touches source='GDELT' rows — every other source is left untouched.
"""
import argparse
import shutil
import sys
from collections import Counter
from datetime import datetime

from models import Crisis, Session, engine
from data_sources import GDELTConnector


def _crisis_to_cap_dict(c):
    """Minimal dict shape GDELTConnector's cap functions expect. Tie-break
    is confidence, not severity — see _cap_fanout_per_source_url's
    docstring for why (sorting by severity measurably skews the surviving
    dataset toward inflated/noisy high-severity rows)."""
    return {
        'id': c.id,
        'title': c.title,
        'source_url': c.source_url,
        'severity': c.severity or 0,
        'confidence': c.confidence or 0,
        'country': c.country,
        'date_start': c.date_start,
        'latitude': c.latitude,
        'longitude': c.longitude,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Actually delete rows (default: dry run)')
    args = parser.parse_args()

    session = Session()
    try:
        gdelt_crises = session.query(Crisis).filter(Crisis.source == 'GDELT').all()
        by_id = {c.id: c for c in gdelt_crises}
        print(f"Loaded {len(gdelt_crises)} GDELT-sourced crises from the live database.")

        # Pass 1: the three geographic/syndication fan-out caps, reusing
        # the exact same functions ingestion runs, in the same order.
        as_dicts = [_crisis_to_cap_dict(c) for c in gdelt_crises]
        after_url_cap = GDELTConnector._cap_fanout_per_source_url(as_dicts)
        after_cluster_cap = GDELTConnector._cap_fanout_per_event_cluster(after_url_cap)
        after_title_day_cap = GDELTConnector._cap_fanout_per_title_day(after_cluster_cap)
        fanout_survivor_ids = {c['id'] for c in after_title_day_cap}
        fanout_dropped = [cid for cid in by_id if cid not in fanout_survivor_ids]

        # Pass 2: per-row content-quality checks against the fan-out
        # survivors — self-referential titles, generic-actor-leading
        # titles, and blank-actor rows under a violent CAMEO root. These
        # predate the ingestion-time filters Phase 21/22 added, so they
        # were never checked against them.
        reasons = Counter()
        drop_ids = list(fanout_dropped)
        for cid in fanout_survivor_ids:
            c = by_id[cid]
            if GDELTConnector._is_self_referential_title(c.title):
                drop_ids.append(cid)
                reasons['self_referential_title'] += 1
            elif GDELTConnector._starts_with_generic_actor_name(c.title):
                drop_ids.append(cid)
                reasons['generic_actor_name'] += 1
            elif GDELTConnector._is_blank_actor_violent_root(c.title, c.analysis):
                drop_ids.append(cid)
                reasons['blank_actor_violent_root'] += 1

        kept_ids = set(by_id) - set(drop_ids)

        print(f"Would keep {len(kept_ids)} rows, drop {len(drop_ids)} rows:")
        print(f"  geographic/syndication fan-out: {len(fanout_dropped)}")
        for reason, count in reasons.items():
            print(f"  {reason}: {count}")

        if not drop_ids:
            print("Nothing to clean up.")
            return

        if not args.apply:
            print("\nDry run only — pass --apply to actually delete these rows.")
            print("Sample of rows that would be dropped (first 10):")
            for cid in drop_ids[:10]:
                c = by_id[cid]
                print(f"  {c.id}  sev={c.severity}  {c.country}  {c.date_start}  {c.title[:70]}")
            return

        backup_path = f"geointel.db.bak-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        db_path = engine.url.database
        if db_path:
            shutil.copy2(db_path, backup_path)
            print(f"Backed up {db_path} -> {backup_path}")
        else:
            print("WARNING: could not resolve a sqlite file path to back up — proceeding without a backup.")

        deleted = session.query(Crisis).filter(Crisis.id.in_(drop_ids)).delete(synchronize_session=False)
        session.commit()
        print(f"Deleted {deleted} near-duplicate GDELT crisis rows.")
    finally:
        session.close()


if __name__ == '__main__':
    sys.exit(main())
