"""
The optional written summary of a cascade result. The model gets a plain fact sheet built from the computed result (trigger, assumptions,
the most exposed countries with their evidence, what could soften it, what is not modelled) and may use nothing else: no number that is
not in the sheet, no forecast, no probability. The text is checked after the fact (every number must appear in the sheet, no probability
wording) and one retry is made before giving up. Cached for a week per fact sheet; "unavailable" without a model rather than a made-up
paragraph. Premium, like the rest of Cascade.
"""
import hashlib
import logging
import re

from cache import cache_get, cache_set
from services.ai_client import AI_MODEL, anthropic_client
from services.scenarios import _PROBABILITY_RE

logger = logging.getLogger(__name__)

TOP_EFFECTS = 12
MAX_FACTS = 7000
CACHE_SECONDS = 7 * 24 * 3600
_NUMBER = re.compile(r'\d[\d,]*\.?\d*')
_FORECAST_WORDS = re.compile(r'\b(will|probab\w*|chance|odds|likelihood|forecast|predict\w*)\b', re.I)


class NarrativeUnavailable(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def facts_for(result):
    """The fact sheet: one fact per line, only what the result contains."""
    t = result['trigger']
    lines = [f"Trigger: {t['label']}: {t['country_name']}" + (f", {t['commodity_label']}" if t.get('commodity_label') else ''),
             f"Assumption: {result['assumes']}"]
    lines += [f'Note: {n}' for n in result.get('notes', [])]
    counts = result['counts']
    lines.append(f"Countries listed: {counts['High']} High, {counts['Moderate']} Moderate, {counts['Low']} Low exposure")
    for e in result['effects'][:TOP_EFFECTS]:
        evidence = ' '.join(x['text'] for x in e['evidence'][:2])
        lines.append(f"{e['name']} ({e['exposure']}; {' and '.join(e['mechanisms']).lower()}; {e['horizon']}): {evidence}")
    lines += [f"Could soften it: {w['text']}" for w in result.get('would_change', [])]
    lines += [f'Not modelled: {n}' for n in result.get('not_modelled', [])]
    return '\n'.join(lines)[:MAX_FACTS]


PROMPT = """You are writing a short summary of a cascade analysis for an intelligence briefing.
Use ONLY the facts below. Write 4 to 6 plain sentences: what the trigger assumes, who is most exposed and why (name the mechanism), how soon,
what could soften it, and what the analysis does not cover. Say "exposed", never "will". Do not forecast, and do not give any probability or chance.
Do not state any number, name or date that is not in the facts. No markup, no list.

FACTS:
%(facts)s"""


def _grounded(text, facts):
    """None when the text is acceptable, else the reason it is not."""
    if _PROBABILITY_RE.search(text) or _FORECAST_WORDS.search(text):
        return 'forecast wording'
    known = {n.rstrip('.,').replace(',', '') for n in _NUMBER.findall(facts)}
    for number in _NUMBER.findall(text):
        if number.rstrip('.,').replace(',', '') not in known:
            return f'number not in the facts: {number}'
    return None


def narrate(result):
    """{'text', 'model'} for a result. Raises NarrativeUnavailable when there is no model, no effects, or the text cannot be grounded."""
    if not result.get('effects'):
        raise NarrativeUnavailable('no_effects')
    if not (anthropic_client and anthropic_client.api_key):
        raise NarrativeUnavailable('no_model')
    facts = facts_for(result)
    key = f'cascade_narrative:{hashlib.sha1(facts.encode("utf-8")).hexdigest()[:16]}'
    cached = cache_get(key)
    if cached:
        return cached
    for attempt in range(2):
        try:
            message = anthropic_client.messages.create(model=AI_MODEL, max_tokens=600,
                                                       messages=[{'role': 'user', 'content': PROMPT % {'facts': facts}}])
            text = message.content[0].text.strip()
        except Exception as e:
            logger.info('[CascadeNarrative] model call failed: %s', e)
            raise NarrativeUnavailable('model_error')
        problem = _grounded(text, facts) if text else 'empty'
        if problem is None:
            out = {'text': text, 'model': AI_MODEL}
            cache_set(key, out, ttl=CACHE_SECONDS)
            return out
        logger.info('[CascadeNarrative] attempt %s rejected: %s', attempt + 1, problem)
    raise NarrativeUnavailable('ungrounded')
