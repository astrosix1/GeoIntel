"""
"How power works": a short plain-language reading of the Factbook's own text on a country's executive, legislature, courts and
constitution. The model is given only that text and told to say nothing that is not in it; a point the text does not cover comes
back empty and is simply not shown. Without an API key, or if the model fails, there is no explanation (the Factbook text
itself is always shown beside it). Remembered for a week per country and per version of the input text.
"""
import hashlib
import json
import logging

from cache import cache_get, cache_set
from services.ai_client import AI_MODEL, anthropic_client

logger = logging.getLogger(__name__)

POINTS = ('head_of_state', 'government', 'legislature', 'courts', 'constitution')
MAX_TEXT = 6000


def _source_text(gov):
    """The Factbook text the explanation may use, as labelled lines."""
    parts = []

    def add(label, value):
        if value:
            parts.append(f'{label}: {value}')

    add('Government type', gov.get('type'))
    add('Chief of state', (gov.get('chief_of_state') or {}).get('text'))
    add('Head of government', (gov.get('head_of_government') or {}).get('text'))
    add('Cabinet', gov.get('cabinet'))
    add('How the executive is chosen', gov.get('election_process'))
    legislature = gov.get('legislature') or {}
    add('Legislature', ' / '.join(x for x in (legislature.get('name'), legislature.get('structure')) if x))
    for chamber in legislature.get('chambers') or []:
        add(f"Chamber ({chamber.get('label')})", '; '.join(x for x in (chamber.get('name'), f"seats {chamber.get('seats')}" if chamber.get('seats') else None,
                                                                         chamber.get('electoral_system'), f"term {chamber.get('term')}" if chamber.get('term') else None) if x))
    judiciary = gov.get('judiciary') or {}
    add('Highest courts', judiciary.get('highest_courts'))
    add('How judges are chosen', judiciary.get('selection'))
    constitution = gov.get('constitution') or {}
    add('Constitution', constitution.get('history'))
    add('Amending the constitution', constitution.get('amendment'))
    add('Legal system', gov.get('legal_system'))
    return '\n'.join(parts)[:MAX_TEXT]


PROMPT = """Below is the CIA World Factbook's own text about how one country is governed. Write a plain-language explanation of who holds power
and how, using ONLY facts stated in that text. Return a single JSON object with exactly these keys:
  "head_of_state", "government", "legislature", "courts", "constitution".
Each value is one or two plain sentences, or null when the text does not cover that point. Do not add facts, dates, names or numbers
that are not in the text. Do not use markup. No text outside the JSON.

TEXT:
%s"""


def explain(cc, gov):
    """{'head_of_state': str|None, ...} or None when there is nothing to explain or no model is available."""
    source = _source_text(gov or {})
    if not source or not (anthropic_client and anthropic_client.api_key):
        return None
    key = f'country_power:{cc}:{hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]}'
    cached = cache_get(key)
    if cached is not None:
        return cached or None
    try:
        message = anthropic_client.messages.create(model=AI_MODEL, max_tokens=700, messages=[{'role': 'user', 'content': PROMPT % source}])
        raw = message.content[0].text
        data = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])
    except Exception as e:
        logger.info('[CountryPower] %s failed: %s', cc, e)
        return None
    out = {p: (data.get(p).strip() if isinstance(data.get(p), str) and data.get(p).strip() else None) for p in POINTS}
    if not any(out.values()):
        return None
    cache_set(key, out, ttl=7 * 24 * 3600)
    return out
