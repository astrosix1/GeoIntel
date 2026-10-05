"""
Shared helpers used across connectors — NewsAPI title cleaning and GDELT's
real-headline fetch both use _clean_article_title.
"""
import re
import requests

from ._shared import logger

# Real headline text (and, for GDELT crises, a refined pin location) for a
# crisis whose only data so far is auto-generated/coarse. GDELT's raw event
# export never includes article text/headlines at all, for copyright
# reasons, so the only way to get real metadata is to fetch the real
# SOURCEURL GDELT already gives us and read the page's own <title>/
# <meta description> tags.
#
# Called from two places with different timing tradeoffs: (1) at sync time,
# bounded-concurrently, by GDELTConnector._resolve_real_titles() — only
# against rows that already survived every fan-out/dedup cap, so it's a few
# hundred real requests per sync, not one per raw parsed row — to resolve
# the real TITLE once so every later reader sees it already real, with no
# lazy-fetch flash; (2) lazily, once, the first time a specific crisis is
# opened, via GET /api/crises/<id>/real-headline, which additionally does
# real AI-extraction + Nominatim location refinement — a heavier, AI-
# involving operation deliberately NOT moved to bulk sync time, so that
# path stays lazy and its own caller is expected to cache the result.
_TITLE_TAG_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta\s+(?:[^>]*?\s+)?name=["\']description["\'][^>]*?content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
# og:image / og:video meta tags. Deliberately NOT one big regex with nested
# `.*?`/`[^>]*?` alternation across the whole (real, often 200KB+) page —
# that construction hit real, confirmed catastrophic backtracking (150+
# seconds on a real news page with no matching tag) once tested live
# against an actual article. Instead: a single linear scan for `<meta ...>`
# tags (bounded per-tag via `[^>]`, so no backtracking blowup), then a
# cheap, bounded check of each tag's own short text for the og:image/video
# property + a content= value, in either attribute order.
_META_TAG_RE = re.compile(r'<meta\s[^>]*>', re.IGNORECASE)
_CONTENT_ATTR_RE = re.compile(r'content=["\'](.*?)["\']', re.IGNORECASE)


def _extract_og_content(html, property_name):
    """First real content= value from a <meta property="{property_name}">
    tag, scanning tags one at a time (each individually bounded) rather
    than one unbounded regex over the whole page. None when absent."""
    needle = f'"{property_name}"'.lower()
    needle_alt = f"'{property_name}'".lower()
    for tag in _META_TAG_RE.findall(html):
        tag_lower = tag.lower()
        if f'property={needle}' in tag_lower or f'property={needle_alt}' in tag_lower:
            content_match = _CONTENT_ATTR_RE.search(tag)
            if content_match:
                return content_match.group(1)
    return None

# A real page's <title> tag, or a news API's own title field, commonly
# either IS just a date (an archive/listicle page) or has the outlet's own
# name appended (" - Source Name" / " | Source Name") — neither is
# something either real source normally cleans up before handing it back,
# and this app previously passed both straight through to the UI
# unvalidated. Shared by fetch_real_page_metadata() below (the real-
# headline lazy-fetch path) and NewsBasedCrisisDetector's NewsAPI title
# assignment — one utility, two call sites.
_DATE_ONLY_TITLE_RE = re.compile(
    r'^\s*(?:'
    r'\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}'
    r'|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}'
    r'|\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+\d{2,4}'
    r')\s*$',
    re.IGNORECASE,
)
_TITLE_SOURCE_SUFFIX_RE = re.compile(r'\s+[-|–—]\s+([A-Za-z0-9][A-Za-z0-9 .&\'’]{1,40})$')


def _clean_article_title(title, source_name=None):
    """Real title text (a plausible trailing outlet-name suffix stripped),
    or None when the title is unusable (empty, or purely a date/archive-
    page title with no real headline content) — the caller is expected to
    fall back to something else real (GDELT: its own auto-generated title;
    NewsAPI: skip the article) rather than show a garbage title."""
    if not title:
        return None
    title = title.strip()
    suffix_match = _TITLE_SOURCE_SUFFIX_RE.search(title)
    if suffix_match:
        suffix = suffix_match.group(1).strip()
        # Strip only when the suffix is a plausible outlet name: matches
        # the real known source, or — when the source isn't known here —
        # looks like one (short, no sentence-ending punctuation inside).
        looks_like_outlet = (
            (source_name and suffix.lower() == source_name.strip().lower())
            or (not source_name and len(suffix) <= 40 and not re.search(r'[.!?]', suffix))
        )
        if looks_like_outlet:
            title = title[:suffix_match.start()].strip()
    if not title or _DATE_ONLY_TITLE_RE.match(title):
        return None
    return title


EXCERPT_CHARS = 1500
_SCRIPT_STYLE_RE = re.compile(r'<(script|style|noscript|svg|nav|header|footer|aside|form)\b[^>]*>.*?</\1>',
                              re.IGNORECASE | re.DOTALL)
_PARAGRAPH_RE = re.compile(r'<p\b[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r'<[^>]+>')


def _body_excerpt(page_html):
    """The first ~1,500 characters of the article's paragraph text, or None.
    Only <p> text of reasonable length is kept, which skips menus and captions."""
    import html as html_module
    stripped = _SCRIPT_STYLE_RE.sub(' ', page_html[:400000])
    parts, total = [], 0
    for raw in _PARAGRAPH_RE.findall(stripped):
        text = re.sub(r'\s+', ' ', html_module.unescape(_TAG_RE.sub(' ', raw))).strip()
        if len(text) < 60:
            continue
        parts.append(text)
        total += len(text)
        if total >= EXCERPT_CHARS:
            break
    excerpt = ' '.join(parts)[:EXCERPT_CHARS].strip()
    return excerpt or None


def fetch_real_page_metadata(url):
    """Real {'title', 'description'} for a live web page (either may be
    None if the page doesn't have one), or None if the fetch fails or the
    URL is missing/malformed. One HTTP request for both fields — not
    GDELT-specific, any crisis with a real source_url could use this."""
    if not url or not url.startswith(('http://', 'https://')):
        return None
    try:
        import html as html_module
        response = requests.get(
            url,
            headers={'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)'},
            timeout=8,
        )
        response.raise_for_status()

        def _clean(raw):
            text = html_module.unescape(raw).strip()
            text = re.sub(r'\s+', ' ', text)
            return text[:300] if text else None

        def _clean_url(raw):
            if not raw:
                return None
            text = html_module.unescape(raw).strip()
            return text if text.startswith(('http://', 'https://')) else None

        title_match = _TITLE_TAG_RE.search(response.text)
        desc_match = _META_DESC_RE.search(response.text)
        raw_title = _clean(title_match.group(1)) if title_match else None
        title = _clean_article_title(raw_title)
        description = _clean(desc_match.group(1)) if desc_match else None
        image_url = _clean_url(_extract_og_content(response.text, 'og:image'))
        video_url = _clean_url(_extract_og_content(response.text, 'og:video'))
        excerpt = _body_excerpt(response.text)
        if title is None and description is None and image_url is None and video_url is None and not excerpt:
            return None
        return {'title': title, 'description': description, 'image_url': image_url, 'video_url': video_url,
                'excerpt': excerpt}
    except Exception as e:
        logger.warning(f"Real page metadata fetch failed for '{url}': {e}")
        return None
