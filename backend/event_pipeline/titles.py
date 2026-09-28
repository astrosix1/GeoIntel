"""
Display titles: clean what a source gives us, or synthesize a readable one.

What was reaching the globe and sidebar:
  - ACLED: the event's ID code as the title (e.g. "UKR12345").
  - GDELT: "Unknown actor — conflict event in Nigeria" templates.
  - NewsAPI: headlines with the outlet appended ("... - Reuters",
    "... | BBC News"), wire tags, and live-blog headlines that are nothing
    but a date ("Russia-Ukraine war live: September 25, 2026").

clean_title() strips outlet names, BREAKING/LIVE-style tags and date
fragments, then rejects whatever is left if it's a date, an ID code, a URL,
a generic label or too short to say anything. choose_title() tries the
source's own title first and then each fallback in turn (the connector
supplies them via candidate['_meta']['fallback_titles']):
  - ACLED: "{sub_event_type} in {location}, {admin1}: N killed"
  - GDELT: a headline recovered from the article URL's slug, else a CAMEO
    phrase ("Russia carries out air strikes on Ukraine in Kharkiv, Ukraine")
  - NewsAPI: the first sentence of the article description
"""
import json
import os
import re
from functools import lru_cache
from urllib.parse import urlsplit, unquote

from .config import get_config
from .normalize import MAX_TITLE_LEN, truncate_words

_CAMEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'cameo_titles.json'
)

# ── patterns ───────────────────────────────────────────────────────────────

_MONTH = (r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|'
          r'sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)')
_WEEKDAY = r'(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?'
_ORD = r'(?:st|nd|rd|th)?'
DATE = (
    rf'(?:{_WEEKDAY},?\s+)?(?:'
    rf'\d{{1,2}}{_ORD}\s+{_MONTH}\.?(?:,?\s+\d{{4}})?'        # 25 September 2026
    rf'|{_MONTH}\.?\s+\d{{1,2}}{_ORD}(?:,?\s+\d{{4}})?'       # Sept. 25, 2026
    rf'|{_MONTH}\.?\s+\d{{4}}'                               # September 2026
    rf'|\d{{4}}-\d{{2}}-\d{{2}}'                              # 2026-09-25
    rf'|\d{{1,2}}[/.]\d{{1,2}}[/.]\d{{2,4}}'                  # 25/09/2026
    rf')'
)
_DATE_ONLY_RE = re.compile(rf'^(?:{DATE}|{_WEEKDAY})$', re.IGNORECASE)

# Separator between a headline and a trailing/leading label. A hyphen only
# counts with spaces around it, so "Russia-Ukraine" is never split.
_SEP = r'(?:\s+[-–—]\s+|\s*[|•·:]\s*)'

_LEADING_DATE_RE = re.compile(rf'^\s*\(?{DATE}\)?(?:{_SEP}|\s*,\s*)', re.IGNORECASE)
_TRAILING_DATE_RE = re.compile(rf'(?:{_SEP}|\s*,\s*|\s+(?=\())\(?{DATE}\)?\s*$', re.IGNORECASE)
_LEADING_DAY_RE = re.compile(r'^\s*day\s+\d{1,4}(?:\s+of\s+[^:|–—-]+)?\s*[:|–—-]\s*', re.IGNORECASE)
_TRAILING_DAY_RE = re.compile(r'(?:' + _SEP + r'|\s*,\s*)day\s+\d{1,4}(?:\s+of\s+.*)?$', re.IGNORECASE)

_LEADING_TAG_RE = re.compile(
    r'^\s*(?:breaking(?:\s+news)?|live(?:\s+updates?|\s+blog)?|update\s*\d*|watch|exclusive|opinion|'
    r'analysis|explainer|video|photos?|just\s+in|developing|latest|factbox|timeline|fact\s+check)'
    r'\s*[:\-–—|]\s*',
    re.IGNORECASE,
)
_TRAILING_LIVE_RE = re.compile(
    r'(?:' + _SEP + r'|\s+)(?:live(?:\s+updates?|\s+blog|\s+news|\s+coverage)?|latest(?:\s+updates|\s+news)?|'
    r'as\s+it\s+happened|updates?)\s*$',
    re.IGNORECASE,
)
_WIRE_TAG_RE = re.compile(r'\s*\((?:reuters|ap|afp|bloomberg|upi|dpa|ians|pti)\)\s*', re.IGNORECASE)
_ID_CODE_RE = re.compile(r'^[A-Z]{2,5}\d{2,}$')
_URLISH_RE = re.compile(r'^(?:https?://|www\.)|^\S+\.(?:com|org|net|gov|info|io|co)(?:/\S*)?$', re.IGNORECASE)
_GENERIC_RE = re.compile(
    r'^(?:news|home|homepage|latest|latest news|live|breaking news|top stories|headlines|world news|'
    r'world|untitled|article|page not found|access denied)$',
    re.IGNORECASE,
)
_WRAP_QUOTES_RE = re.compile(r'^[\"“”\'‘’]+(.+?)[\"“”\'‘’]+$')
_EDGE_PUNCT = ' \t-–—|•·:,;'

_SMALL_WORDS = {'a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or', 'but', 'by',
                'with', 'from', 'as', 'vs', 'over', 'into', 'near', 'after', 'amid'}
# Upper-cased acronyms that are also ordinary lower-case words — left alone
# when re-casing a URL slug, where "us" or "who" is far more often a word.
_AMBIGUOUS_IN_SLUGS = {'US', 'WHO', 'AI', 'IT', 'AM', 'PM', 'MP', 'MPS', 'AU', 'IS', 'SAF'}

_SLUG_EXT_RE = re.compile(r'\.(?:s?html?|php\d?|aspx?|cms|ece|jsp|story|amp)$', re.IGNORECASE)
_SLUG_DROP_LEADING = {'breaking', 'live', 'exclusive', 'watch', 'update', 'video', 'opinion', 'news', 'amp'}


def _title_cfg():
    return get_config().get('titles', {})


@lru_cache(maxsize=1)
def _acronyms():
    return frozenset(a.upper() for a in _title_cfg().get('acronyms', []))


@lru_cache(maxsize=1)
def _cameo_phrases():
    with open(_CAMEO_PATH, 'r', encoding='utf-8') as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith('_')}


# ── casing ─────────────────────────────────────────────────────────────────

def headline_case(text, from_slug=False):
    """Title-case a phrase, keeping known acronyms upper-case and short
    function words lower-case (except the first word)."""
    acronyms = _acronyms() - (_AMBIGUOUS_IN_SLUGS if from_slug else set())
    words = text.split()
    out = []
    for i, word in enumerate(words):
        parts = []
        for part in word.split('-'):
            core = part.strip('.,;:!?()"\'')
            if core.upper() in acronyms:
                parts.append(part.upper())
            elif i > 0 and core.lower() in _SMALL_WORDS:
                parts.append(part.lower())
            else:
                parts.append(part[:1].upper() + part[1:].lower())
        out.append('-'.join(parts))
    return ' '.join(out)


def _is_all_caps(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


# ── outlet stripping ───────────────────────────────────────────────────────

def _letters(text):
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())


def _host_letters(url):
    if not url:
        return '', ''
    try:
        host = (urlsplit(url).hostname or '').lower()
    except ValueError:
        return '', ''
    if host.startswith('www.'):
        host = host[4:]
    stem = host.split('.')[0] if host else ''
    return _letters(host), stem


def _is_outlet_label(label, outlet, url):
    """Is `label` (a trailing/leading headline segment) the publisher's
    name rather than part of the story?"""
    label = label.strip(_EDGE_PUNCT + '()')
    if not label or len(label.split()) > 6:
        return False
    norm = _letters(label)
    if not norm:
        return False
    names = [outlet] if outlet else []
    names += _title_cfg().get('known_outlets', [])
    if any(norm == _letters(n) for n in names if n):
        return True
    # Domain match — the label must cover most of the domain name (or vice
    # versa), so "Kyiv" is never mistaken for kyivindependent.com while
    # "BBC News" (bbc.co.uk) and "Times of India" (timesofindia...) are.
    host, stem = _host_letters(url)
    if stem and len(stem) >= 3:
        if norm == stem:
            return True
        if stem in norm and len(stem) >= 0.4 * len(norm):
            return True
        if norm in host and len(norm) >= 0.6 * len(stem):
            return True
    return bool(_URLISH_RE.match(label))


def _strip_outlet(text, outlet, url):
    for _ in range(3):
        parts = re.split(_SEP, text)
        if len(parts) < 2:
            break
        if _is_outlet_label(parts[-1], outlet, url):
            # Remove only the last separator + label, keep inner separators.
            text = re.sub(_SEP + re.escape(parts[-1]) + r'\s*$', '', text)
            continue
        if _is_outlet_label(parts[0], outlet, url):
            text = re.sub(r'^\s*' + re.escape(parts[0]) + _SEP, '', text)
            continue
        break
    return text


# ── cleaning ───────────────────────────────────────────────────────────────

def clean_title(raw, outlet=None, url=None, strict=True):
    """Cleaned display title, or None if nothing usable remains.

    strict=True applies the minimum-length rules meant for headlines of
    unknown quality (source titles, URL slugs). Titles this module
    synthesized itself are passed with strict=False: they're known to be
    well-formed, just sometimes short ("Bombing in Mogadishu, Somalia")."""
    if not raw:
        return None
    text = ' '.join(str(raw).split())
    match = _WRAP_QUOTES_RE.match(text)
    if match:
        text = match.group(1)

    previous = None
    while previous != text:
        previous = text
        text = _WIRE_TAG_RE.sub(' ', text).strip()
        text = _strip_outlet(text, outlet, url)
        text = _LEADING_TAG_RE.sub('', text)
        text = _LEADING_DATE_RE.sub('', text)
        text = _TRAILING_DATE_RE.sub('', text)
        text = _LEADING_DAY_RE.sub('', text)
        text = _TRAILING_DAY_RE.sub('', text)
        text = _TRAILING_LIVE_RE.sub('', text)
        text = ' '.join(text.split()).strip(_EDGE_PUNCT)

    if not text:
        return None
    if _DATE_ONLY_RE.match(text) or _ID_CODE_RE.match(text) or _URLISH_RE.match(text) \
            or _GENERIC_RE.match(text):
        return None
    if strict:
        cfg = _title_cfg()
        if len(text.split()) < cfg.get('min_words', 3) or len(text) < cfg.get('min_chars', 15):
            return None

    if _is_all_caps(text):
        text = headline_case(text)
    else:
        text = text[:1].upper() + text[1:]
    return truncate_words(text, MAX_TITLE_LEN)


def choose_title(raw, outlet=None, url=None, fallbacks=()):
    """First usable title: the source's own, then each (text, strict)
    fallback in order. Returns (title, synthesized) or (None, False)."""
    title = clean_title(raw, outlet=outlet, url=url, strict=True)
    if title:
        return title, False
    for text, strict in fallbacks or ():
        title = clean_title(text, outlet=outlet, url=url, strict=strict)
        if title:
            return title, True
    return None, False


# ── synthesis ──────────────────────────────────────────────────────────────

def first_sentence(text):
    """First sentence of a description, for when the headline is unusable."""
    if not text:
        return None
    text = ' '.join(str(text).split())
    text = re.sub(r'\s*(?:\[\+?\d+ chars\]|…|\.\.\.)\s*$', '', text)  # NewsAPI truncation markers
    sentence = re.split(r'(?<=[.!?])\s+(?=[A-Z"“])', text, maxsplit=1)[0]
    return sentence.rstrip('.').strip() or None


def acled_title(event):
    """"Armed clash in Pokrovsk, Donetsk: 4 killed" from ACLED's own fields."""
    kind = (event.get('sub_event_type') or event.get('event_type') or '').strip()
    if not kind:
        return None
    place_parts = []
    for part in (event.get('location'), event.get('admin1')):
        part = (part or '').strip()
        if part and part.lower() not in (p.lower() for p in place_parts):
            place_parts.append(part)
    if not place_parts and event.get('country'):
        place_parts.append(event['country'].strip())
    title = kind[:1].upper() + kind[1:]
    if place_parts:
        title += ' in ' + ', '.join(place_parts)
    try:
        fatalities = int(event.get('fatalities') or 0)
    except (TypeError, ValueError):
        fatalities = 0
    if fatalities > 0:
        title += f": {fatalities} killed"
    return title


def slug_title(url):
    """A headline recovered from an article URL's slug, e.g.
    /breaking-5-miners-killed-others-injured-in-plateau-attack/ ->
    "5 Miners Killed Others Injured in Plateau Attack". None when the URL
    has no word-like slug (numeric ids, index pages)."""
    if not url:
        return None
    try:
        path = unquote(urlsplit(url).path)
    except ValueError:
        return None
    segments = [s for s in path.split('/') if s]
    for segment in reversed(segments[-2:]):
        segment = _SLUG_EXT_RE.sub('', segment)
        words = [w for w in re.split(r'[-_+]+', segment) if w]
        words = [
            w for w in words
            if not (w.isdigit() and len(w) >= 4)                                    # ids, years
            and not re.fullmatch(r'(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{6,}', w, re.I)  # hashes
        ]
        while words and words[0].lower() in _SLUG_DROP_LEADING:
            words.pop(0)
        alpha = [w for w in words if re.search(r'[a-z]', w, re.IGNORECASE)]
        if len(alpha) >= 4 and len(alpha) >= 0.6 * len(words):
            return headline_case(' '.join(words).lower(), from_slug=True)
    return None


def _gdelt_place(full_name):
    parts = []
    for part in (full_name or '').split(','):
        part = part.strip().rstrip('*').strip()
        if part and part.lower() not in (p.lower() for p in parts):
            parts.append(part)
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else f"{parts[0]}, {parts[-1]}"


def gdelt_title(actor1, actor2, event_code, place_full_name, base_code=None, root_code=None):
    """CAMEO-phrased title: "{Actor1} {verb} {Actor2} in {place}", or
    "{noun} involving {Actor} in {place}" / "{noun} in {place}" when an
    actor is missing. None for codes with no phrasing."""
    phrases = _cameo_phrases()
    code = str(event_code or '')
    phrase = (phrases.get(str(base_code or '')) or phrases.get(code[:3])
              or phrases.get(str(root_code or '')) or phrases.get(code[:2]))
    if not phrase:
        return None
    a1 = headline_case(actor1.strip()) if actor1 and actor1.strip() else None
    a2 = headline_case(actor2.strip()) if actor2 and actor2.strip() else None
    if a1 and a2 and a1.lower() != a2.lower():
        title = f"{a1} {phrase['verb']} {a2}"
    elif a1 or a2:
        title = f"{phrase['noun']} involving {a1 or a2}"
    else:
        title = phrase['noun']
    place = _gdelt_place(place_full_name)
    if place:
        title += f" in {place}"
    return title
