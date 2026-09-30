"""Escalation trajectory analysis for a crisis."""
from models import Session, Crisis, CrisisSnapshot


def analyze_escalation(crisis_id, _crisis=None):
    """
    Analyze escalation trajectory for a crisis using real CrisisSnapshot
    history (see DataAggregator.snapshot_severity_history — one row per
    active crisis per hourly scheduled sync). Returns None if the crisis
    doesn't exist. Returns an explicit 'insufficient_data' result — not a
    fabricated trend — when fewer than 2 real snapshots exist yet for this
    crisis (e.g. it was created since the last sync ran). This function
    used to invent a "7-day history" via deterministic backward
    extrapolation from the single current severity value, which guaranteed
    any high-severity crisis always showed as "escalating" regardless of
    its real trajectory — there was never any actual historical reading
    behind it. That fabrication is gone; a real trend now requires real data.

    If the caller already has the Crisis row loaded (e.g. iterating a query
    result), pass it as `_crisis` to skip the redundant crisis lookup — a
    session is still opened regardless, to query real snapshot history.
    """
    session = Session()
    try:
        crisis = _crisis if _crisis is not None else session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None

        snapshots = (
            session.query(CrisisSnapshot)
            .filter(CrisisSnapshot.crisis_id == crisis_id)
            .order_by(CrisisSnapshot.recorded_at.asc())
            .all()
        )

        if len(snapshots) < 2:
            return {
                'trend': 'insufficient_data',
                'severity_change': None,
                'velocity': None,
                'current_severity': crisis.severity,
                'warning': None,
                'history': [{'severity': s.severity, 'date': s.recorded_at.isoformat()} for s in snapshots],
                'message': 'Not enough historical readings yet to compute a trend for this crisis.',
            }

        severities = [s.severity for s in snapshots]
        days_span = max((snapshots[-1].recorded_at - snapshots[0].recorded_at).total_seconds() / 86400, 1 / 24)
        severity_change = severities[-1] - severities[0]
        velocity = severity_change / days_span

        if velocity > 5:
            trend = 'escalating'
        elif velocity < -5:
            trend = 'de-escalating'
        else:
            trend = 'stable'

        warning = None
        if velocity > 10:
            warning = '🔴 RAPID ESCALATION'
        elif velocity > 5:
            warning = '🟠 ESCALATING'
        elif velocity < -10:
            warning = '🟢 RAPID DE-ESCALATION'

        return {
            'trend': trend,
            'severity_change': round(severity_change),
            'velocity': round(velocity, 1),
            'current_severity': crisis.severity,
            'warning': warning,
            'history': [{'severity': s.severity, 'date': s.recorded_at.isoformat()} for s in snapshots],
        }
    finally:
        session.close()
