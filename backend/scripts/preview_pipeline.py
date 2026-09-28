#!/usr/bin/env python3
"""
Dry run of the event pipeline against LIVE source data — fetches from the
real connectors, runs event_pipeline.process_batch, and prints what would
be kept or rejected (with reason codes, sample titles and a severity
histogram). Nothing is written to the database.

Use it to sanity-check a change to config/event_filters.json or a pipeline
stage before it reaches the hourly sync:

    cd backend
    python scripts/preview_pipeline.py --source gdelt
    python scripts/preview_pipeline.py --source newsapi --samples 30
    python scripts/preview_pipeline.py --source all --no-db

--no-db points the process at a throwaway in-memory database, so stakeholder
matching (which reads the Actor roster) just finds nothing instead of
touching your real database. Without it the roster is read, never written.
NewsAPI and ACLED need their keys in .env; GDELT needs nothing. When ACLED
isn't configured its connector returns built-in sample data, which this
script labels as such.
"""
import argparse
import os
import sys
from collections import Counter

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--source', choices=['gdelt', 'newsapi', 'acled', 'all'], default='gdelt')
    parser.add_argument('--samples', type=int, default=20, help='kept titles to print')
    parser.add_argument('--no-db', action='store_true', help='use an in-memory database')
    return parser.parse_args()


def fetch(source):
    import data_sources as ds
    if source == 'gdelt':
        return 'GDELT', ds.GDELTConnector.fetch_recent_events()
    if source == 'newsapi':
        return 'NewsAPI', ds.NewsBasedCrisisDetector.extract_crises_from_news(days=7)
    rows = ds.ACLEDConnector.fetch_recent_events(days=30)
    if rows and all(str(r.get('source')) == 'Sample Data' for r in rows):
        print("  (ACLED not configured — these are the built-in sample crises)")
    return 'ACLED', rows


def main():
    args = parse_args()
    if args.no_db:
        os.environ['DATABASE_URL'] = 'sqlite://'
    sys.path.insert(0, BACKEND_DIR)
    os.chdir(BACKEND_DIR)
    from dotenv import load_dotenv
    load_dotenv()

    import event_pipeline

    sources = ['gdelt', 'newsapi', 'acled'] if args.source == 'all' else [args.source]
    report = event_pipeline.PipelineReport(label='preview')
    kept = []
    for source in sources:
        print(f"\nFetching {source}...")
        name, candidates = fetch(source)
        result = event_pipeline.process_batch(candidates, name, report=report)
        kept.extend(result.kept)

    summary = report.to_dict()
    print("\n" + "=" * 70)
    print(report.summary_line())
    print("=" * 70)
    for name, stats in summary['sources'].items():
        print(f"\n{name}: received {stats['received']}, kept {stats['kept']}")
        for label, key in (('severity', 'severity_bands'), ('global impact', 'impact_bands')):
            bands = stats.get(key) or {}
            if bands:
                print(f"  {label} bands: " + ', '.join(
                    f"{b}={bands.get(b, 0)}" for b in ('critical', 'high', 'elevated', 'low')))
        for reason, count in sorted(stats['rejected'].items(), key=lambda kv: -kv[1]):
            print(f"  rejected {reason}: {count}")
            for title in stats['rejected_samples'].get(reason, []):
                print(f"      - {title}")

    print(f"\nSample kept titles (up to {args.samples}):")
    by_type = Counter(c.get('type') for c in kept)
    for c in kept[: args.samples]:
        print(f"  [{c.get('source')}] sev={c.get('severity'):>3} imp={c.get('global_impact', 0):>3} {c.get('type'):<17} "
              f"{c.get('country')[:18]:<18} {c.get('title')[:90]}")
    if by_type:
        print("\nKept by type: " + ', '.join(f"{t}={n}" for t, n in by_type.most_common()))


if __name__ == '__main__':
    main()
