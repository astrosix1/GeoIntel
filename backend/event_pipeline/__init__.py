"""
Event quality pipeline: every candidate crisis from every connector (ACLED,
GDELT, NewsAPI, multilingual NewsAPI) passes through process_batch() before
it is written, so filtering, location validation, dedup and scoring live in
one deterministic, unit-tested place instead of being scattered across
connectors. See docs/EVENT_FILTERING.md for the full design.

Stages run in order, and each one either keeps a candidate (possibly
modifying it) or rejects it with a reason code recorded in the report:

    normalize  -> required fields, coordinate sanity, column-length clamps
    batch_dedup -> one candidate per id within a batch

Later phases add relevance, location, titles, cross-source dedup/merge and
scoring as further stages. Stages are pure functions of the candidate (plus
config), so each is testable without a database or network.
"""
from dataclasses import dataclass, field

from .normalize import normalize_candidate
from .report import PipelineReport, remember, recent_reports  # noqa: F401 (re-exported)

META_KEY = '_meta'  # transient per-candidate context for stages; never persisted


@dataclass
class PipelineResult:
    kept: list = field(default_factory=list)
    rejected: list = field(default_factory=list)   # (reason, candidate)
    report: PipelineReport = None


def _stage_normalize(candidate, state):
    return normalize_candidate(candidate)


def _stage_batch_dedup(candidate, state):
    seen = state.setdefault('seen_ids', set())
    if candidate['id'] in seen:
        return 'duplicate_in_batch'
    seen.add(candidate['id'])
    return None


STAGES = (
    ('normalize', _stage_normalize),
    ('batch_dedup', _stage_batch_dedup),
)


def process_batch(candidates, source, report=None):
    """Run `candidates` (crisis dicts from one connector) through every
    stage. Returns a PipelineResult whose `kept` dicts are ready for
    DataAggregator._upsert_crisis (transient `_meta` removed)."""
    report = report or PipelineReport(label=source)
    result = PipelineResult(report=report)
    state = {}

    for candidate in candidates or []:
        if not candidate:
            continue
        report.record_received(source)
        reason = None
        for _name, stage in STAGES:
            reason = stage(candidate, state)
            if reason:
                break
        if reason:
            report.record_rejected(source, reason, candidate)
            result.rejected.append((reason, candidate))
            continue
        candidate.pop(META_KEY, None)
        report.record_kept(source, candidate)
        result.kept.append(candidate)

    return result
