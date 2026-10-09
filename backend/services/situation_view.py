"""
The situation view: what can be said about a group of stories (services/situations.py) from real data alone, with no model
and no key. A timeline of the stories, their scale, the main headline and the angles that differ most, a few short sentences
the outlets repeat (quoted and attributed, never rewritten), and any casualty figures the headlines or excerpts state outright
(each shown with where it is stated, never added up). With a model key the briefing adds prose on top; this view is what is
there without one.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from math import sqrt

from cache import cache_get, cache_set
from data_sources import fetch_real_page_metadata
from models import Session, Crisis, Situation
from services.event_analysis import build_pattern
from services.situations import headline_of, tokens_of
from services.stories import outlet_of, significant_tokens

logger = logging.getLogger(__name__)

EXCERPT_STORIES = 6          # how many stories' pages are read for sentences
FETCH_TIMEOUT = 12           # seconds for all the page reads together
ANGLES = 3
SENTENCES = 4
SENTENCE_MIN, SENTENCE_MAX = 45, 260
VIEW_TTL = 20 * 60
EXCERPT_TTL = 6 * 3600

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z"“])')
_NUMBER_WORDS = {w: i for i, w in enumerate(
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split())}
_NUM = r'(\d[\d,]*|' + '|'.join(w for w in _NUMBER_WORDS if w != 'zero') + r')'
_FIGURE = re.compile(
    r'\b' + _NUM + r'(?:\s+(?:more\s+)?(?:people|civilians|soldiers|police|officers|children|students|migrants|protesters|others|dead|victims))?'
    r'(?:\s+(?:were|was|have been|has been|had been|are|is))?(?:\s+(?:reportedly|also|later|confirmed|officially))?'
    r'\s+(killed|dead|injured|wounded|hurt)\b', re.I)
_VERB_FIRST = re.compile(r'\b(kills?|killed|injures?|injured|wounds?|wounded)\s+(?:at least\s+)?' + _NUM + r'\b', re.I)


def _count(text):
    text = text.lower().replace(',', '')
    return int(text) if text.isdigit() else _NUMBER_WORDS.get(text)


_ABBREVIATIONS = frozenset('mr mrs ms dr st mt gen lt col sgt capt jan feb mar apr jun jul aug sep sept oct nov dec no vs etc'.split())
SENTENCE_CAP = 320


def split_sentences(text):
    """Sentences of `text` with their start offsets. A full stop after an abbreviation or an initial ("U.S.", "Oct.", "Dr.") does not end one."""
    spans, start = [], 0
    for match in re.finditer(r'[.!?]["\u201d\')]*\s+(?=["\u201c\']?[A-Z0-9])', text):
        before = text[start:match.start() + 1].split()
        last = before[-1].rstrip('.!?"\u201d\')').lower() if before else ''
        if last in _ABBREVIATIONS or (len(last.replace('.', '')) == 1 and text[match.start()] == '.') or re.fullmatch(r'(?:[a-z]\.)+[a-z]', last):
            continue
        spans.append((start, match.start() + 1))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return [(a, text[a:b]) for a, b in spans if text[a:b].strip()]


def _sentence_around(text, match):
    """The whole sentence a figure appears in, trimmed only at a clause break when it is very long, never mid-word."""
    for start, sentence in split_sentences(text):
        if start <= match.start() < start + len(sentence):
            sentence = ' '.join(sentence.split())
            if len(sentence) <= SENTENCE_CAP:
                return sentence
            at = match.start() - start
            lead = ''
            if at > SENTENCE_CAP // 2:                                   # begin at the clause before the figure
                cut = max(sentence.rfind(', ', 0, at), sentence.rfind('; ', 0, at), sentence.rfind(' -- ', 0, at))
                if cut > 0:
                    sentence, lead = sentence[cut + 2:].lstrip('- '), '\u2026 '
            if len(sentence) > SENTENCE_CAP:
                sentence = sentence[:SENTENCE_CAP].rsplit(' ', 1)[0].rstrip(',;:') + ' \u2026'
            return lead + sentence
    return ' '.join(text[max(0, match.start() - 120):match.end() + 120].split())


def stated_figures(texts):
    """Casualty statements found in `texts` (a list of strings): [{'sentence', 'figures': [{'count', 'kind'}], 'stated_in': [index...]}].
    Each is the whole sentence the figures appear in, quoted as written, so a figure for one place is not read as a total. The same
    sentence in several texts is one entry that lists every text it appears in. Nothing is added up."""
    entries = []     # [{'sentence', 'tokens', 'figures': {(count, kind)}, 'stated_in': set}]
    for index, text in enumerate(texts):
        text = text or ''
        for regex, group_count, group_kind in ((_FIGURE, 1, 2), (_VERB_FIRST, 2, 1)):
            for match in regex.finditer(text):
                count, word = _count(match.group(group_count)), match.group(group_kind).lower()
                kind = 'killed' if word in ('killed', 'dead') or word.startswith('kill') else 'injured'
                if count is None or not 0 < count < 100000:
                    continue
                sentence = _sentence_around(text, match)
                tokens = significant_tokens(sentence)
                entry = next((e for e in entries if len(e['tokens'] & tokens) / max(1, min(len(e['tokens']), len(tokens))) >= 0.75), None)
                if entry is None:
                    entry = {'sentence': sentence, 'tokens': tokens, 'figures': set(), 'stated_in': set()}
                    entries.append(entry)
                entry['figures'].add((count, kind))
                entry['stated_in'].add(index)
    entries.sort(key=lambda e: (-len(e['stated_in']), -len(e['figures'])))
    return [{'sentence': e['sentence'], 'figures': [{'count': c, 'kind': k} for c, k in sorted(e['figures'], key=lambda f: (f[1] != 'killed', -f[0]))],
             'stated_in': sorted(e['stated_in'])} for e in entries]


def pick_angles(headlines, limit=ANGLES):
    """The headlines that differ most from each other (farthest-first on word overlap), as indexes. The first is index 0."""
    sets = [tokens_of(h) for h in headlines]
    chosen = [0] if headlines else []
    while len(chosen) < min(limit, len(headlines)):
        def distance(i):
            return min(1 - (len(sets[i] & sets[j]) / len(sets[i] | sets[j]) if sets[i] | sets[j] else 0) for j in chosen)
        rest = [i for i in range(len(headlines)) if i not in chosen]
        best = max(rest, key=distance)
        if distance(best) < 0.35:        # the rest say the same thing in other words
            break
        chosen.append(best)
    return chosen


def key_sentences(stories, limit=SENTENCES):
    """Short sentences from the stories' text that the most other stories echo. `stories` is a list of
    {'text': excerpt, 'title': headline, 'outlet', 'url'}. Returns [{'text', 'outlet', 'url', 'echoed_by'}]."""
    docs = [tokens_of(s['title']) | tokens_of(s.get('text') or '') for s in stories]
    support = {}
    for d in docs:
        for t in d:
            support[t] = support.get(t, 0) + 1
    n = len(docs)
    cap = max(2, int(0.8 * n))
    candidates = []
    for i, s in enumerate(stories):
        for sentence in _SENTENCE_END.split(s.get('text') or ''):
            sentence = ' '.join(sentence.split())
            if not SENTENCE_MIN <= len(sentence) <= SENTENCE_MAX:
                continue
            toks = tokens_of(sentence)
            useful = [t for t in toks if 2 <= support.get(t, 0) <= cap]
            if len(useful) < 3:
                continue
            echoed = {j for j, d in enumerate(docs) if j != i and len(d & toks) >= 3}
            candidates.append((sum(support[t] - 1 for t in useful) / sqrt(len(toks)), sentence, toks, i, len(echoed)))
    candidates.sort(key=lambda c: -c[0])
    out, kept = [], []
    for score, sentence, toks, i, echoed in candidates:
        if any(len(toks & k) / len(toks | k) >= 0.5 for k in kept):
            continue
        kept.append(toks)
        out.append({'text': sentence, 'outlet': stories[i]['outlet'], 'url': stories[i]['url'], 'echoed_by': echoed})
        if len(out) == limit:
            break
    return out


def _excerpt(url, stored):
    """The story's article text: the stored excerpt, else a page read remembered for a few hours (even a failed one)."""
    if stored:
        return stored
    if not url:
        return None
    key = f'situation_excerpt:{url}'
    cached = cache_get(key)
    if cached is not None:
        return cached or None
    page = None
    try:
        page = fetch_real_page_metadata(url)
    except Exception as e:
        logger.warning(f"[Situation] page read failed for {url}: {e}")
    text = ' '.join(filter(None, [page and page.get('description'), page and page.get('excerpt')])) if page else ''
    cache_set(key, text, ttl=EXCERPT_TTL)
    return text or None


def build_view(session, situation, members):
    members = sorted(members, key=lambda c: (c.date_start, c.id))
    lead = next((c for c in members if c.id == situation.id), members[0])
    main = max(members, key=lambda c: (c.source_count or 1, -c.date_start.timestamp()))
    heads = [headline_of(c.title) for c in ([main] + [c for c in members if c is not main])]
    ordered = [main] + [c for c in members if c is not main]
    angles = [{'id': ordered[i].id, 'headline': heads[i], 'outlet': outlet_of(ordered[i].source_url)} for i in pick_angles(heads)[1:]]

    readers = sorted(members, key=lambda c: (-(c.source_count or 1), c.date_start))[:EXCERPT_STORIES]
    pool = ThreadPoolExecutor(max_workers=EXCERPT_STORIES)
    futures = {c.id: pool.submit(_excerpt, c.source_url, c.article_excerpt) for c in readers}
    texts = {}
    for cid, fut in futures.items():
        try:
            texts[cid] = fut.result(timeout=FETCH_TIMEOUT)
        except (FutureTimeout, Exception):
            texts[cid] = None
    pool.shutdown(wait=False)

    stories = [{'text': texts.get(c.id) or '', 'title': headline_of(c.title), 'outlet': outlet_of(c.source_url), 'url': c.source_url}
               for c in members]
    sentences = key_sentences(stories) if any(s['text'] for s in stories) else []

    corpus = [f"{s['title']}. {s['text']}" for s in stories]
    figures = []
    for fig in stated_figures(corpus):
        places = [{'outlet': stories[i]['outlet'], 'url': stories[i]['url']} for i in fig['stated_in'][:3]]
        figures.append({'sentence': fig['sentence'], 'figures': fig['figures'], 'stated_by': len(fig['stated_in']), 'where': places})

    return {
        'id': situation.id,
        'title': headline_of(main.title),
        'main_id': main.id,
        'country': lead.country,
        'story_count': len(members),
        'outlet_count': situation.source_total,
        'first_at': members[0].date_start.isoformat(),
        'last_at': members[-1].date_start.isoformat(),
        'stories': [dict(c.to_dict(), headline=headline_of(c.title), outlet=outlet_of(c.source_url)) for c in members],
        'angles': angles,
        'key_sentences': sentences,
        'figures': figures[:5],
        'pattern': build_pattern(session, lead),
        'read_pages': sum(1 for t in texts.values() if t),
    }


def get_situation_view(crisis_id):
    """The view for the situation this event belongs to, or None when it stands alone."""
    key = f'situation_view:v1:{crisis_id}'
    cached = cache_get(key)
    if cached is not None:
        return cached or None
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        sid = crisis and crisis.situation_id
        situation = sid and session.get(Situation, sid)
        if not situation:
            cache_set(key, {}, ttl=VIEW_TTL)
            return None
        members = (session.query(Crisis).filter(Crisis.situation_id == sid, Crisis.is_active.is_(True), Crisis.merged_into.is_(None)).all())
        if len(members) < 2:
            cache_set(key, {}, ttl=VIEW_TTL)
            return None
        view = build_view(session, situation, members)
    finally:
        session.close()
    cache_set(key, view, ttl=VIEW_TTL)
    return view
