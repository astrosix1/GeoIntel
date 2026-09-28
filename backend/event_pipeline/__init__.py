"""
Event quality pipeline: every candidate crisis from every connector (ACLED,
GDELT, NewsAPI, multilingual NewsAPI) passes through process_batch() before
it is written, so filtering, location validation, dedup and scoring live in
one deterministic, unit-tested place instead of being scattered across
connectors. See docs/EVENT_FILTERING.md for the full design.

Stages run in order, and each one either keeps a candidate (possibly
modifying it) or rejects it with a reason code recorded in the report:

    normalize   -> required fields, coordinate sanity, column-length clamps
    relevance   -> geopolitical-event and outlet checks per source (relevance.py)
    location    -> canonical country, coordinates inside it, precision (location.py)
    titles      -> clean the source title or synthesize one (titles.py)
    batch_dedup -> one candidate per id within a batch

then the survivors are clustered (dedup.py) so each real-world event is one
kept dict, with every merged report kept as provenance, and each event is
scored (scoring.py: local severity + global_impact) from all its reports.

Stages are pure functions of the candidate (plus
config), so each is testable without a database or network.
"""
from dataclasses import dataclass, field

from .normalize import normalize_candidate
from .titles import choose_title
from .relevance import check_relevance
from .location import check_location
from .titles import gdelt_title
from .dedup import cluster_batch, source_record
from .scoring import extract_features, merge_features, apply_scores
from .report import PipelineReport, remember, recent_reports  # noqa: F401 (re-exported)

META_KEY = '_meta'  # transient per-candidate context for stages; never persisted


@dataclass
class PipelineResult:
    kept: list = field(default_factory=list)       # one clean crisis dict per event (cluster primary)
    sources: list = field(default_factory=list)    # per kept event: crisis_sources dicts, primary first
    metas: list = field(default_factory=list)      # per kept event: the primary's transient _meta
    features: list = field(default_factory=list)   # per kept event: scoring inputs (all its reports merged)
    rejected: list = field(default_factory=list)   # (reason, candidate)
    merged: int = 0                                # reports folded into another report of the same event
    report: PipelineReport = None


def _stage_titles(candidate, state):
    meta = candidate.get(META_KEY) or {}
    fallbacks = list(meta.get('fallback_titles', ()))
    cameo = meta.get('cameo')
    if cameo:
        # Built here, not in the connector, so it names the place the
        # location stage settled on (which may differ from GDELT's).
        fallbacks.append((gdelt_title(place_full_name=meta.get('place_full_name'), **cameo), False))
    title, synthesized = choose_title(
        candidate.get('title'),
        outlet=meta.get('outlet'),
        url=meta.get('url'),
        fallbacks=fallbacks,
    )
    if not title:
        return 'no_usable_title'
    candidate['title'] = title
    meta['title_synthesized'] = synthesized
    candidate[META_KEY] = meta
    return None


def _stage_normalize(candidate, state):
    return normalize_candidate(candidate)


def _stage_relevance(candidate, state):
    return check_relevance(candidate, candidate.get(META_KEY) or {})


def _stage_location(candidate, state):
    return check_location(candidate, candidate.setdefault(META_KEY, {}))


def _stage_batch_dedup(candidate, state):
    seen = state.setdefault('seen_ids', set())
    if candidate['id'] in seen:
        return 'duplicate_in_batch'
    seen.add(candidate['id'])
    return None


STAGES = (
    ('normalize', _stage_normalize),
    ('relevance', _stage_relevance),
    ('location', _stage_location),
    ('titles', _stage_titles),
    ('batch_dedup', _stage_batch_dedup),
)


def process_batch(candidates, source, report=None):
    """Run `candidates` (crisis dicts from one connector) through every
    stage, then cluster the survivors so each real-world event appears once
    (dedup.cluster_batch). Returns a PipelineResult whose `kept` dicts are
    ready for DataAggregator to store — transient `_meta` removed, pipeline
    columns (country_code, location_precision, source_url, source_count)
    filled in — with the provenance of every merged report in `sources`."""
    report = report or PipelineReport(label=source)
    result = PipelineResult(report=report)
    state = {}
    survivors = []

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
        survivors.append((candidate, candidate.pop(META_KEY, None) or {}))

    for cluster in cluster_batch(survivors):
        primary, meta = cluster[0]
        sources, seen = [], set()
        for candidate, member_meta in cluster:
            record = source_record(candidate, member_meta)
            if record['url_key'] not in seen:
                seen.add(record['url_key'])
                sources.append(record)
        primary['country_code'] = meta.get('country_code')
        primary['location_precision'] = meta.get('location_precision')
        primary['source_url'] = meta.get('url')
        primary['source_count'] = len(sources)
        features = None
        for candidate, member_meta in cluster:
            features = merge_features(features, extract_features(candidate, member_meta))
        apply_scores(primary, features, source_count=len(sources))
        if len(cluster) > 1:
            result.merged += len(cluster) - 1
            report.record_merged(source, len(cluster) - 1)
        report.record_kept(source, primary)
        result.kept.append(primary)
        result.sources.append(sources)
        result.metas.append(meta)
        result.features.append(features)

    return result
