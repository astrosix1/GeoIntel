"""The structured form of an event briefing: a short summary, key points that each cite numbered sources, and what the sources do not
say. The model fills a forced tool; this module validates it so only real source numbers survive and nothing is unbounded."""

MAX_POINTS = 5
MAX_UNKNOWNS = 3
MAX_SUMMARY = 600
MAX_POINT = 400
MAX_UNKNOWN = 200

BRIEFING_TOOL = {
    'name': 'write_briefing',
    'description': 'Write the briefing for this event from the numbered sources and excerpts only.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'summary': {'type': 'string', 'description': 'Two sentences: what happened, where, and why it matters now.'},
            'key_points': {
                'type': 'array',
                'description': '3 to 5 specific points (actors, places, figures). Each cites the source numbers it rests on; '
                               'a point that is your own judgment has an empty list.',
                'items': {
                    'type': 'object',
                    'properties': {'text': {'type': 'string'}, 'sources': {'type': 'array', 'items': {'type': 'integer'}}},
                    'required': ['text', 'sources'],
                },
            },
            'unknowns': {
                'type': 'array',
                'description': 'Up to 3 things the sources do not say or disagree on, phrased as "not reported" or as the '
                               'disagreement. Never a guess.',
                'items': {'type': 'string'},
            },
        },
        'required': ['summary', 'key_points', 'unknowns'],
    },
}


def _clean(value, limit):
    if not isinstance(value, str):
        return None
    value = ' '.join(value.split())[:limit]
    return value or None


def validate(payload, source_count):
    """{'summary', 'key_points': [{'text', 'sources'}], 'unknowns'} or None when unusable. Source numbers outside 1..source_count are dropped."""
    if not isinstance(payload, dict):
        return None
    summary = _clean(payload.get('summary'), MAX_SUMMARY)
    points = []
    for item in payload.get('key_points') or []:
        if not isinstance(item, dict):
            continue
        text = _clean(item.get('text'), MAX_POINT)
        if not text:
            continue
        cites = sorted({n for n in (item.get('sources') or []) if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= source_count})
        points.append({'text': text, 'sources': cites})
        if len(points) == MAX_POINTS:
            break
    unknowns = [u for u in (_clean(x, MAX_UNKNOWN) for x in (payload.get('unknowns') or [])) if u][:MAX_UNKNOWNS]
    if not summary or not points:
        return None
    return {'summary': summary, 'key_points': points, 'unknowns': unknowns}


def as_text(structured):
    """Plain text of the structured briefing, for consumers that only read `briefing`."""
    lines = [structured['summary'], '']
    for p in structured['key_points']:
        lines.append(f"- {p['text']}" + ''.join(f" [{n}]" for n in p['sources']))
    if structured['unknowns']:
        lines += ['', 'Not reported: ' + '; '.join(structured['unknowns'])]
    return '\n'.join(lines)
