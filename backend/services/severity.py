"""Strict severity: a written five-level scale, scored by code from stated facts.

The AI never outputs a score. It only extracts facts from the article
(services/story_facts.py); this module turns facts into a level and a number,
and records the reasons ("basis") so the UI can show them.

Levels: Minor 0-19, Moderate 20-39, Serious 40-59, Severe 60-79, Critical 80-100.

Rules (all in the tables below so they can be read and tuned):
  * Statements (talks, criticism, threats) are capped at Serious (49).
  * With no extracted facts the score is a headline-only estimate from the feed's
    own verb intensity, capped at Serious (59), and says so.
  * Stated deaths set a floor; mass-casualty or chemical/biological/nuclear cues
    floor higher; corroboration adds up to +10.
  * Critical needs two or more independent outlets.
"""
import json
import logging

logger = logging.getLogger(__name__)

LEVELS = (
    (80, 5, 'Critical'),
    (60, 4, 'Severe'),
    (40, 3, 'Serious'),
    (20, 2, 'Moderate'),
    (0, 1, 'Minor'),
)

STATEMENT_CAP = 49
HEADLINE_ONLY_CAP = 59
NO_CORROBORATION_CAP = 79
CORROBORATION_PER_EXTRA_OUTLET = 2
CORROBORATION_MAX = 10

# Starting score by what kind of event the article describes (physical events).
TYPE_BASE = {
    'armed_conflict': 40, 'terrorism': 45, 'natural_disaster': 35, 'accident': 25, 'crime': 20,
    'protest': 20, 'health': 25, 'political': 15, 'diplomacy': 10, 'economic': 15, 'other': 20,
}
# (minimum killed, floor), checked from the top.
KILLED_FLOORS = ((100, 90), (10, 80), (3, 65), (1, 55))
INJURED_FLOORS = ((100, 65), (10, 45), (1, 30))
CUE_FLOORS = {'mass_casualty': 90, 'chemical_bio_nuclear': 90}
CUE_BONUS = {'infrastructure': 8, 'state_actors': 5, 'ongoing': 5}


def level_of(score):
    """(level 1-5, name) for a 0-100 score."""
    for floor, level, name in LEVELS:
        if score >= floor:
            return level, name
    return 1, 'Minor'


def _plural(n, word):
    return f'{n} {word}'


def score_story(feed, event_kind, facts, source_count):
    """{'score', 'level', 'name', 'feed', 'basis': [str]} for one story.

    `feed` is the source's own intensity (0-100, GDELT: -Goldstein*10); `facts`
    is the validated extraction dict or None."""
    feed = max(0, min(100, int(feed or 0)))
    sources = max(1, int(source_count or 1))
    basis = []
    corroboration = min(CORROBORATION_MAX, (sources - 1) * CORROBORATION_PER_EXTRA_OUTLET)
    cap = 100

    statement = event_kind == 'statement' or bool(facts and facts.get('is_statement'))
    if statement:
        score = round(feed * 0.4)
        cap = STATEMENT_CAP
        basis.append('A statement or talks, with no physical event: capped at Serious')
    elif not facts:
        score = 20 + round(feed * 0.35)
        cap = HEADLINE_ONLY_CAP
        basis.append('Headline-only estimate: the article has not been read yet, so it is capped at Serious')
    else:
        event_type = facts.get('event_type') or 'other'
        score = TYPE_BASE.get(event_type, TYPE_BASE['other'])
        basis.append(f"Event type: {event_type.replace('_', ' ')}")
        killed, injured = facts.get('killed'), facts.get('injured')
        if killed:
            floor = next((f for n, f in KILLED_FLOORS if killed >= n), 0)
            if floor > score:
                score = floor
            basis.append(f'{_plural(killed, "killed")}, stated in the article')
        if injured:
            floor = next((f for n, f in INJURED_FLOORS if injured >= n), 0)
            if floor > score:
                score = floor
            basis.append(f'{_plural(injured, "injured")}, stated in the article')
        cues = facts.get('scale_cues') or []
        for cue in cues:
            if cue in CUE_FLOORS:
                score = max(score, CUE_FLOORS[cue])
                basis.append(f"Scale: {cue.replace('_', ' ')}")
        for cue in cues:
            if cue in CUE_BONUS:
                score += CUE_BONUS[cue]
                basis.append(f"Scale: {cue.replace('_', ' ')}")

    if sources > 1:
        score += corroboration
        basis.append(f'Reported by {sources} outlets')
    else:
        basis.append('Single outlet')

    score = max(0, min(score, cap, 100))
    if score >= 80 and sources < 2:
        score = NO_CORROBORATION_CAP
        basis.append('Critical needs two or more independent outlets')
    level, name = level_of(score)
    return {'score': score, 'level': level, 'name': name, 'feed': feed, 'basis': basis}


def stored_facts(crisis):
    try:
        data = json.loads(crisis.facts) if crisis.facts else None
    except ValueError:
        return None
    return data if isinstance(data, dict) and data else None


def feed_intensity(crisis):
    """The source's own intensity for a stored story: kept in the basis once
    scored, otherwise the stored severity (the feed's raw value before scoring)."""
    try:
        basis = json.loads(crisis.severity_basis) if crisis.severity_basis else None
    except ValueError:
        basis = None
    if isinstance(basis, dict) and isinstance(basis.get('feed'), int):
        return basis['feed']
    return crisis.severity or 0


def rescore(crisis):
    """Recompute and set severity, severity_level and severity_basis on a GDELT
    story row (caller commits). Other sources keep their own severity."""
    if crisis.source != 'GDELT':
        return None
    result = score_story(feed_intensity(crisis), crisis.event_kind, stored_facts(crisis), crisis.source_count)
    crisis.severity = result['score']
    crisis.severity_level = result['level']
    crisis.severity_basis = json.dumps({'feed': result['feed'], 'basis': result['basis'], 'name': result['name']})
    return result


def rescore_all(session=None):
    """Rescore every active GDELT story. Idempotent; CLI: python -m services.severity."""
    from models import Session, Crisis
    own = session is None
    session = session or Session()
    count = 0
    try:
        for crisis in session.query(Crisis).filter(Crisis.source == 'GDELT', Crisis.is_active.is_(True)):
            rescore(crisis)
            count += 1
        session.commit()
    finally:
        if own:
            session.close()
    return count


if __name__ == '__main__':
    print(f'Rescored {rescore_all()} stories')
