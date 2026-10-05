"""AI-generated branch scenarios: several ways a crisis could unfold.

Honesty rules, in line with the rest of this app (see history.py's analogy
"strength" word and the removed heuristic Forecast tab):
  - Likelihood is a qualitative word, never a percentage or probability. No
    model or dataset here could back a number, so a number would be invented.
  - Every response is labelled AI-generated and speculative, lists its
    assumptions, and says which real facts it was grounded in.
  - There is no static fallback: without a model there is nothing honest to
    show, so callers get ScenariosUnavailable and the UI says so.
"""
import logging
import re
from datetime import datetime

from models import Session, Crisis
from cache import cache_get, cache_set
from data_sources import fetch_real_page_metadata
from services.ai_client import anthropic_client, AI_MODEL
from services.escalation import analyze_escalation
from services.history import get_relevant_relationships
from services.story_facts import story_stamp, story_context_lines

logger = logging.getLogger(__name__)

# Scenarios for an event don't change by the hour, and every call is paid.
CACHE_TTL_SECONDS = 12 * 60 * 60
MAX_TOKENS = 1800
MAX_SCENARIOS = 4
MIN_SCENARIOS = 2

LIKELIHOODS = ('less likely', 'plausible', 'more likely')

DISCLAIMER = (
    "These scenarios are AI-generated possibilities, not predictions or reporting. They are built "
    "from the facts listed under 'Based on' plus the model's general knowledge. Verify anything "
    "important independently before relying on it."
)

# "30% chance", "probability of 40", "odds are 2" ... — numeric probabilities
# are exactly the fabricated precision this feature must not show.
_PROBABILITY_RE = re.compile(
    r'\d+\s*(?:%|percent)\s*(?:chance|probability|likelihood|likely|odds)'
    r'|(?:probability|chance|odds)\b[^.\n]{0,40}?\b(?:of|is|are|at)\s+(?:about\s+|roughly\s+|around\s+|approximately\s+)?\d+',
    re.IGNORECASE,
)

SCENARIO_TOOL = {
    'name': 'record_scenarios',
    'description': 'Record the scenarios for how this crisis could unfold.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'scenarios': {
                'type': 'array',
                'minItems': 3,
                'maxItems': MAX_SCENARIOS,
                'items': {
                    'type': 'object',
                    'properties': {
                        'title': {'type': 'string'},
                        'likelihood': {'type': 'string', 'enum': list(LIKELIHOODS)},
                        'timeframe': {'type': 'string'},
                        'summary': {'type': 'string'},
                        'what_would_drive_it': {'type': 'array', 'items': {'type': 'string'}},
                        'watch_for': {'type': 'array', 'items': {'type': 'string'}},
                        'who_is_affected': {'type': 'array', 'items': {'type': 'string'}},
                    },
                    'required': ['title', 'likelihood', 'timeframe', 'summary',
                                 'what_would_drive_it', 'watch_for', 'who_is_affected'],
                },
            },
            'assumptions': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['scenarios', 'assumptions'],
    },
}


class ScenariosUnavailable(Exception):
    """No model configured, or the model call/validation failed."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ''


def _text_list(value, limit=200, max_items=5):
    if not isinstance(value, list):
        return []
    items = (_text(v, limit) for v in value)
    return [item for item in items if item][:max_items]


def _validate(payload):
    """(scenarios, assumptions) cleaned from the model's tool input. Drops any
    scenario that is malformed, has an unknown likelihood word, or states a
    numeric probability; raises ScenariosUnavailable if fewer than
    MIN_SCENARIOS survive."""
    raw = payload.get('scenarios') if isinstance(payload, dict) else None
    scenarios = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        scenario = {
            'title': _text(item.get('title'), 120),
            'likelihood': _text(item.get('likelihood'), 20).lower(),
            'timeframe': _text(item.get('timeframe'), 60),
            'summary': _text(item.get('summary'), 700),
            'what_would_drive_it': _text_list(item.get('what_would_drive_it')),
            'watch_for': _text_list(item.get('watch_for')),
            'who_is_affected': _text_list(item.get('who_is_affected')),
        }
        if not scenario['title'] or not scenario['summary']:
            continue
        if scenario['likelihood'] not in LIKELIHOODS:
            continue
        everything = ' '.join(
            [scenario['title'], scenario['timeframe'], scenario['summary']]
            + scenario['what_would_drive_it'] + scenario['watch_for'] + scenario['who_is_affected']
        )
        if _PROBABILITY_RE.search(everything):
            continue
        scenarios.append(scenario)
        if len(scenarios) == MAX_SCENARIOS:
            break

    if len(scenarios) < MIN_SCENARIOS:
        raise ScenariosUnavailable('invalid_model_output')

    assumptions = [a for a in _text_list(payload.get('assumptions'), 250, 6) if not _PROBABILITY_RE.search(a)]
    return scenarios, assumptions


def _build_prompt(context):
    return f"""You are helping a journalist or analyst think through how a geopolitical situation could develop. Using ONLY the crisis context below for facts about the current situation, write 3 or 4 distinct scenarios for how it could unfold.

Rules:
- Cover the range: at least one de-escalation or resolution path, one where things persist roughly as they are, and one escalation path. A fourth wildcard scenario is optional.
- For "likelihood" use only one of: "less likely", "plausible", "more likely" (relative to the other scenarios). NEVER give percentages, odds or numeric probabilities anywhere.
- Treat the context as the only established facts. Anything else you rely on (background knowledge, how such situations usually go) must appear in "assumptions", not be stated as fact about this event.
- Do not invent figures, dates, quotes or named individuals that are not in the context. If the context is thin, say so in "assumptions" and keep the scenarios general rather than padding them with detail.
- These are possibilities, not predictions. Be concrete about what would drive each one and what an observer could watch for.

Crisis context:
{context}"""


def _build_context(crisis, escalation, description, relationships):
    lines = [
        f"Title: {crisis.title}",
        f"Country/location: {crisis.country}",
        f"Type: {crisis.type}",
        f"Severity score: {crisis.severity}/100 (derived from the source event's conflict intensity)",
    ]
    trend = escalation.get('trend') if escalation else None
    if trend and trend != 'insufficient_data':
        lines.append(f"Observed severity trend: {trend}")
    else:
        lines.append("Observed severity trend: not enough history to say")
    lines.extend(story_context_lines(crisis))
    if description:
        lines.append(f"Description from the source article: {description}")
    else:
        lines.append("No source article text is available beyond the title.")
    if relationships:
        facts = '; '.join(f"{r.actor_a}-{r.actor_b}: {r.type}, \"{r.label}\"" for r in relationships)
        lines.append(f"Curated relationship record for the actors involved: {facts}")
    return '\n'.join(lines)


def generate_scenarios(crisis_id):
    """Scenario dict for a crisis, or None if the crisis doesn't exist.
    Raises ScenariosUnavailable when there's no API key or the model call or
    its output fails. Cached for 12 hours; failures are never cached."""
    cache_key = f"scenarios:{crisis_id}"
    stamp = story_stamp(crisis_id)
    cached = cache_get(cache_key)
    if cached is not None and cached.get('story_stamp') == stamp:
        return cached

    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None
        if not (anthropic_client and anthropic_client.api_key):
            raise ScenariosUnavailable('ai_not_configured')

        escalation = analyze_escalation(crisis_id, _crisis=crisis)
        relationships = get_relevant_relationships(session, crisis)
        description = None
        if crisis.source_url:
            metadata = fetch_real_page_metadata(crisis.source_url)
            description = metadata.get('description') if metadata else None

        context = _build_context(crisis, escalation, description, relationships)
        based_on = {
            'severity': crisis.severity,
            'trend': (escalation or {}).get('trend'),
            'source_text': bool(description),
            'relationships': [f"{r.actor_a}–{r.actor_b}: {r.label}" for r in relationships],
        }
    finally:
        session.close()

    try:
        message = anthropic_client.messages.create(
            model=AI_MODEL,
            max_tokens=MAX_TOKENS,
            tools=[SCENARIO_TOOL],
            tool_choice={'type': 'tool', 'name': SCENARIO_TOOL['name']},
            messages=[{'role': 'user', 'content': _build_prompt(context)}],
        )
        block = next((b for b in message.content if getattr(b, 'type', None) == 'tool_use'), None)
        if block is None:
            raise ScenariosUnavailable('no_model_output')
        scenarios, assumptions = _validate(block.input)
    except ScenariosUnavailable:
        raise
    except Exception as e:
        logger.error(f"Scenario generation failed for {crisis_id}: {e}")
        raise ScenariosUnavailable('model_error') from e

    result = {
        'scenarios': scenarios,
        'assumptions': assumptions,
        'based_on': based_on,
        'disclaimer': DISCLAIMER,
        'model': AI_MODEL,
        'timestamp': datetime.utcnow().isoformat(),
    }
    result['story_stamp'] = stamp
    cache_set(cache_key, result, ttl=CACHE_TTL_SECONDS)
    return result
