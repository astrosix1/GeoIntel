"""
What the Global/Local classifier would do to the events already in the database. Changes nothing.

Usage (from backend/):  python scripts/scope_report.py [days=7] [samples=40]

Prints the new split against the current one, how many events matched a term list at all (the rest only keep their old side),
which terms decide the most events, and random examples of events that would change side, so the term lists can be tuned.
"""
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Session, Crisis  # noqa: E402
from services.scope import classify  # noqa: E402


def _summary(facts):
    try:
        return (json.loads(facts) or {}).get('summary') or '' if facts else ''
    except (ValueError, TypeError):
        return ''


def main(days=7, samples=40):
    session = Session()
    try:
        rows = (session.query(Crisis)
                .filter(Crisis.is_active.is_(True), Crisis.merged_into.is_(None), Crisis.date_start >= datetime.utcnow() - timedelta(days=days))
                .all())
        cross, rules, terms = Counter(), Counter(), Counter()
        moved = {('global', 'local'): [], ('local', 'global'): []}
        for r in rows:
            old = r.scope or 'global'
            out = classify(f'{r.title} {_summary(r.facts)}', place_specific=bool(r.location_refined_name) or (r.location_confidence or 0) >= 85, noise=(old == 'local'))
            cross[(old, out['scope'])] += 1
            rules[out['rule']] += 1
            terms.update(out['global'] if out['scope'] == 'global' else out['local'])
            if old != out['scope']:
                moved[(old, out['scope'])].append((r.title, out))
        print(f'{len(rows)} events from the last {days} days\n')
        print('current -> new')
        for (old, new), n in sorted(cross.items()):
            print(f'  {old:>6} -> {new:<6} {n:>6}  ({n / len(rows):.1%})')
        print('\nwhy')
        for rule, n in rules.most_common():
            print(f'  {rule:<36} {n:>6}  ({n / len(rows):.1%})')
        print('\nterms that decided the most events')
        for term, n in terms.most_common(25):
            print(f'  {n:>5}  {term}')
        for (old, new), items in moved.items():
            print(f'\n{old} -> {new}: {len(items)} events; {min(samples, len(items))} at random')
            for title, out in random.sample(items, min(samples, len(items))):
                print(f'  [{out["rule"]}] {title[:100]}  <- {", ".join((out["global"] if new == "global" else out["local"])[:4])}')
    finally:
        session.close()


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7, int(sys.argv[2]) if len(sys.argv) > 2 else 40)
