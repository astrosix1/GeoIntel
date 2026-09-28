"""
PipelineReport — what the pipeline kept, rejected and why, per source.

Every rejection carries a reason code, so tuning a threshold in
config/event_filters.json is a matter of reading these counts rather than
guessing. The last few reports are kept in memory for
GET /api/admin/pipeline-report.
"""
from collections import Counter, defaultdict, deque
from datetime import datetime

_MAX_SAMPLES_PER_REASON = 3
_HISTORY_SIZE = 24  # one per hourly sync = a day of history

_history = deque(maxlen=_HISTORY_SIZE)


def severity_band(score):
    if score is None:
        return 'unknown'
    if score >= 80:
        return 'critical'
    if score >= 60:
        return 'high'
    if score >= 35:
        return 'elevated'
    return 'low'


class PipelineReport:
    def __init__(self, label='sync'):
        self.label = label
        self.started_at = datetime.utcnow()
        self.received = Counter()
        self.kept = Counter()
        self.merged = Counter()                         # reports folded into another report of the same event
        self.rejected = defaultdict(Counter)            # source -> reason -> count
        self.samples = defaultdict(list)                # (source, reason) -> [title, ...]
        self.severity_bands = defaultdict(Counter)      # source -> band -> count

    def record_received(self, source, n=1):
        self.received[source] += n

    def record_kept(self, source, candidate):
        self.kept[source] += 1
        self.severity_bands[source][severity_band(candidate.get('severity'))] += 1

    def record_merged(self, source, n=1):
        self.merged[source] += n

    def record_rejected(self, source, reason, candidate=None):
        self.rejected[source][reason] += 1
        samples = self.samples[(source, reason)]
        if candidate is not None and len(samples) < _MAX_SAMPLES_PER_REASON:
            meta = candidate.get('_meta') or {}
            label = (candidate.get('title') or meta.get('headline') or meta.get('url')
                     or candidate.get('id') or '')
            samples.append(str(label)[:120])

    def merge(self, other):
        """Fold another report (e.g. one source's batch) into this one."""
        self.received.update(other.received)
        self.kept.update(other.kept)
        self.merged.update(other.merged)
        for source, reasons in other.rejected.items():
            self.rejected[source].update(reasons)
        for key, titles in other.samples.items():
            room = _MAX_SAMPLES_PER_REASON - len(self.samples[key])
            if room > 0:
                self.samples[key].extend(titles[:room])
        for source, bands in other.severity_bands.items():
            self.severity_bands[source].update(bands)
        return self

    def to_dict(self):
        sources = sorted(set(self.received) | set(self.kept) | set(self.rejected))
        return {
            'label': self.label,
            'started_at': self.started_at.isoformat(),
            'totals': {
                'received': sum(self.received.values()),
                'kept': sum(self.kept.values()),
                'merged': sum(self.merged.values()),
                'rejected': sum(sum(r.values()) for r in self.rejected.values()),
            },
            'sources': {
                s: {
                    'received': self.received[s],
                    'kept': self.kept[s],
                    'merged': self.merged[s],
                    'rejected': dict(self.rejected[s]),
                    'rejected_samples': {
                        reason: self.samples[(s, reason)] for reason in self.rejected[s]
                    },
                    'severity_bands': dict(self.severity_bands[s]),
                }
                for s in sources
            },
        }

    def summary_line(self):
        parts = []
        for s in sorted(set(self.received) | set(self.kept)):
            rejected = sum(self.rejected[s].values())
            reasons = ', '.join(f"{r}={n}" for r, n in self.rejected[s].most_common(4))
            merged = f", {self.merged[s]} merged" if self.merged[s] else ''
            parts.append(f"{s}: {self.received[s]} in, {self.kept[s]} kept{merged}, {rejected} rejected"
                         + (f" ({reasons})" if reasons else ''))
        return f"[pipeline:{self.label}] " + ('; '.join(parts) or 'no candidates')


def remember(report):
    _history.append(report.to_dict())


def recent_reports():
    """Newest first."""
    return list(reversed(_history))
