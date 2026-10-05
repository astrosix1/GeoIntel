"""One extraction call per story: the place and the facts the article states.

A small model reads the article's headline and excerpt and records only what the
text says: the specific place, whether it is a statement (talks, criticism) or
something that happened, killed/injured counts, and a few scale cues from a fixed
list. Plain code turns those facts into a severity later (the model never outputs
a score).

Rules that keep this honest:
  * A number is recorded only when the article states it; otherwise it is null.
  * Everything is validated: fixed lists only, bounded non-negative integers.
  * A definite result, including "nothing usable", is stored in `crises.facts`
    with `facts_extracted_at` and never repeated. A temporary failure (no key,
    model outage) is not stored, so it is retried later.
"""
import json
import logging
from datetime import datetime

from data_sources import fetch_real_page_metadata
from models import Session, Crisis
from services.ai_client import anthropic_client, AI_FACTS_MODEL

logger = logging.getLogger(__name__)

EVENT_TYPES = (
    'armed_conflict', 'terrorism', 'protest', 'natural_disaster', 'accident', 'crime',
    'political', 'diplomacy', 'economic', 'health', 'other',
)
SCALE_CUES = ('mass_casualty', 'infrastructure', 'chemical_bio_nuclear', 'state_actors', 'ongoing')
MAX_COUNT = 1_000_000
MAX_TOKENS = 400
MAX_TEXT_CHARS = 1800

FACTS_TOOL = {
    'name': 'record_facts',
    'description': 'Record only what this article states about the event.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'place': {'type': ['string', 'null'],
                      'description': 'Most specific real place of the event (building, town, region), or null.'},
            'country': {'type': ['string', 'null']},
            'is_statement': {'type': 'boolean',
                             'description': 'True for talks, criticism, threats, announcements: nothing physical happened.'},
            'event_type': {'type': 'string', 'enum': list(EVENT_TYPES)},
            'killed': {'type': ['integer', 'null'], 'description': 'Deaths the article states, else null. Never estimate.'},
            'injured': {'type': ['integer', 'null'], 'description': 'Injuries the article states, else null. Never estimate.'},
            'scale_cues': {'type': 'array', 'items': {'type': 'string', 'enum': list(SCALE_CUES)}},
            'summary': {'type': 'string', 'description': 'One factual sentence.'},
            'confidence': {'type': 'string', 'enum': ['low', 'medium', 'high']},
        },
        'required': ['place', 'is_statement', 'event_type', 'killed', 'injured', 'scale_cues', 'summary', 'confidence'],
    },
}

PROMPT = (
    "Extract facts from this news text. Record only what the text itself states: if it gives no "
    "number of deaths or injuries use null, never estimate. 'place' is the specific place where the "
    "event happened, not a place mentioned in passing; null if unclear. Scale cues only when the text "
    "supports them.\n\n{text}"
)


def facts_available():
    return bool(anthropic_client and getattr(anthropic_client, 'api_key', None))


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= MAX_COUNT else None


def _text(value, limit):
    if not isinstance(value, str):
        return None
    value = ' '.join(value.split())[:limit]
    return value or None


def validate(payload):
    """Clean facts from the model's tool input, or None when it is unusable."""
    if not isinstance(payload, dict) or not isinstance(payload.get('is_statement'), bool):
        return None
    event_type = payload.get('event_type')
    cues = payload.get('scale_cues')
    confidence = payload.get('confidence')
    return {
        'place': _text(payload.get('place'), 200),
        'country': _text(payload.get('country'), 100),
        'is_statement': payload['is_statement'],
        'event_type': event_type if event_type in EVENT_TYPES else 'other',
        'killed': _count(payload.get('killed')),
        'injured': _count(payload.get('injured')),
        'scale_cues': sorted({c for c in cues if c in SCALE_CUES}) if isinstance(cues, list) else [],
        'summary': _text(payload.get('summary'), 300),
        'confidence': confidence if confidence in ('low', 'medium', 'high') else 'low',
    }


def extract_facts(text):
    """(facts, failed). `failed` means the call itself errored (retry later);
    facts is None with failed False means the model gave nothing usable."""
    if not facts_available():
        return None, True
    try:
        message = anthropic_client.messages.create(
            model=AI_FACTS_MODEL,
            max_tokens=MAX_TOKENS,
            tools=[FACTS_TOOL],
            tool_choice={'type': 'tool', 'name': FACTS_TOOL['name']},
            messages=[{'role': 'user', 'content': PROMPT.format(text=text[:MAX_TEXT_CHARS])}],
        )
        block = next((b for b in message.content if getattr(b, 'type', None) == 'tool_use'), None)
        return (validate(block.input) if block is not None else None), False
    except Exception as e:
        logger.warning(f"Fact extraction failed: {e}")
        return None, True


def stored_facts(crisis):
    """The saved facts dict, or None (not extracted yet, or nothing usable)."""
    if not crisis.facts:
        return None
    try:
        data = json.loads(crisis.facts)
    except ValueError:
        return None
    return data if isinstance(data, dict) and data else None


def ensure_facts(crisis_id):
    """{'status': 'done'|'none'|'unavailable'|'not_found', 'facts'?}.

    Idempotent: a story with a recorded result returns it without any call. The
    article is fetched once and its excerpt kept on the row.
    """
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if crisis is None:
            return {'status': 'not_found'}
        if crisis.facts_extracted_at is not None:
            facts = stored_facts(crisis)
            return {'status': 'done', 'facts': facts} if facts else {'status': 'none'}
        url, title, excerpt = crisis.source_url, crisis.title, crisis.article_excerpt
    finally:
        session.close()

    if not facts_available():
        return {'status': 'unavailable', 'reason': 'ai_not_configured'}

    description = None
    if not excerpt and url:
        page = fetch_real_page_metadata(url)
        if page:
            excerpt, description = page.get('excerpt'), page.get('description')
            title = page.get('title') or title
    text = ' '.join(filter(None, [title, description, excerpt]))
    if not excerpt and not description:
        _record(crisis_id, None, excerpt)       # dead, blocked or empty page: will not improve
        return {'status': 'none'}

    facts, failed = extract_facts(text)
    if failed:
        return {'status': 'unavailable', 'reason': 'ai_failed'}
    _record(crisis_id, facts, excerpt)
    return {'status': 'done', 'facts': facts} if facts else {'status': 'none'}


def _record(crisis_id, facts, excerpt):
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if crisis is None:
            return
        crisis.facts = json.dumps(facts) if facts else None
        crisis.facts_extracted_at = datetime.utcnow()
        if excerpt:
            crisis.article_excerpt = excerpt
        from services.severity import rescore
        rescore(crisis)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Could not record facts for {crisis_id}: {e}")
        raise
    finally:
        session.close()


def story_stamp(crisis_id):
    """A short string that changes when a new source merges into the story or its
    facts arrive, so cached analyses and scenarios are rebuilt only then."""
    session = Session()
    try:
        row = session.query(Crisis.source_count, Crisis.facts_extracted_at).filter(Crisis.id == crisis_id).first()
    finally:
        session.close()
    if row is None:
        return None
    return f"{row[0] or 1}:{row[1].isoformat() if row[1] else '-'}"


def story_context_lines(crisis):
    """Plain-text lines describing what the story's facts and severity basis state,
    for the briefing and scenario prompts. Empty when nothing was extracted."""
    lines = []
    facts = stored_facts(crisis)
    if facts:
        if facts.get('summary'):
            lines.append(f"Extracted summary: {facts['summary']}")
        if facts.get('place'):
            lines.append(f"Place: {facts['place']}")
        if facts.get('killed') is not None:
            lines.append(f"Killed (stated in the article): {facts['killed']}")
        if facts.get('injured') is not None:
            lines.append(f"Injured (stated in the article): {facts['injured']}")
        if facts.get('scale_cues'):
            lines.append("Scale cues: " + ', '.join(c.replace('_', ' ') for c in facts['scale_cues']))
    try:
        basis = json.loads(crisis.severity_basis) if crisis.severity_basis else None
    except ValueError:
        basis = None
    if isinstance(basis, dict) and basis.get('basis'):
        lines.append(f"Severity rating {basis.get('name', '')}: " + '; '.join(basis['basis']))
    if (crisis.source_count or 1) > 1:
        lines.append(f"This story merges reports from {crisis.source_count} outlets; say where they disagree.")
    return lines
