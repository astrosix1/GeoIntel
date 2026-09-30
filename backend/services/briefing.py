"""AI-powered (with honest static fallback) current-situation briefing for
a crisis. Serves the "extensive analysis of the event" requirement in the
Analysis sidebar — kept because the new UI still needs this real logic,
not because the old AI-tab UI is coming back."""
import logging
import re
from datetime import datetime

try:
    import requests
except Exception:
    requests = None

from models import Session, Crisis, News
from cache import cache_get, cache_set
from data_sources import fetch_real_page_metadata
from services.ai_client import anthropic_client
from services.escalation import analyze_escalation
from services.economic import get_economic_impact
from services.reliability import calculate_source_reliability

logger = logging.getLogger(__name__)


def fetch_wikipedia_image(country, title):
    """
    Fetch a representative image from Wikipedia article for the crisis country/title.
    Returns { src, caption } or None.
    """
    if not requests:
        return None

    # Bug fix: `title.split(' ')[0:3]` previously produced a *list* of words
    # (e.g. ['Conflict-related', 'event', 'in']), not a string — that list's
    # repr was embedded literally into the Wikipedia URL below, which
    # Wikipedia would just as happily 404/hang on rather than raise a clear
    # error. Join the first few words back into a real search term instead.
    title_term = ' '.join(title.split(' ')[:3]) if title and ' ' in title else title
    terms = [country, title_term]
    terms = [t for t in terms if t]

    for term in terms:
        try:
            from urllib.parse import quote
            url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{quote(term)}'
            r = requests.get(url, timeout=3, headers={
                'Accept': 'application/json',
                'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)',
            })
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get('thumbnail', {}).get('source'):
                # Use Wikipedia's own thumbnail URL exactly as given — real,
                # confirmed-working. Naively rewriting the /Npx- segment to a
                # larger size (a size this specific asset wasn't rendered at)
                # produces a real, confirmed 400 from Wikimedia's thumb
                # servers for some images (e.g. certain flag SVGs), i.e. a
                # broken image — worse than the smaller-but-real default.
                src = data['thumbnail']['source']
                caption = data.get('description') or data.get('title') or term
                return {'src': src, 'caption': caption}
        except Exception as e:
            logger.debug(f"Wiki image fetch failed for '{term}': {e}")
            continue

    return None


def generate_ai_briefing(crisis_id):
    """
    Generate AI-powered briefing summary using Claude API.
    Returns structured brief with briefing text and Wikipedia image.
    Briefings are cached for 1 hour to avoid redundant Anthropic API calls.
    """
    # ── Cache check ──────────────────────────────────────────────────────────
    cache_key = f"briefing:{crisis_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.info(f"[Briefing] Cache hit for crisis {crisis_id}")
        return cached

    logger.info(f"[Briefing] Cache miss for crisis {crisis_id} — generating via Claude API")

    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None

        # Gather context. Journalists/commentators using this briefing need to
        # be able to trace claims back to a real source, so pull enough
        # headlines (with outlet + link, not just a title) to cite from, and
        # number them up front — the prompt below tells Claude to cite by
        # that number rather than inventing its own reference format.
        news = (session.query(News)
                .filter(News.crisis_id == crisis_id)
                .order_by(News.published_at.desc())
                .limit(10).all())
        escalation = analyze_escalation(crisis_id)
        economic = get_economic_impact(crisis_id)
        reliability = calculate_source_reliability(crisis_id)

        numbered_sources = []
        for i, n in enumerate(news, 1):
            pub = n.published_at.strftime('%Y-%m-%d') if n.published_at else 'undated'
            numbered_sources.append({
                'n': i,
                'title': n.title,
                'source': n.source or 'Unknown outlet',
                'url': n.url or '',
                'published': pub,
            })
        # News.crisis_id is never populated by any ingestion connector today
        # (a real, separate bug — the query above matches zero rows for
        # every crisis, not just thin ones), so numbered_sources is empty
        # here in practice regardless of how much real reporting exists.
        # crisis.source_url IS real and already populated for the GDELT
        # majority (used elsewhere in this function for excerpt text) —
        # surface it as a real, citable source too instead of leaving it
        # only implicit in the prose.
        if crisis.source_url and not any(s['url'] == crisis.source_url for s in numbered_sources):
            numbered_sources.append({
                'n': len(numbered_sources) + 1,
                'title': crisis.title,
                'source': crisis.source or 'Unknown outlet',
                'url': crisis.source_url,
                'published': crisis.date_start.strftime('%Y-%m-%d') if crisis.date_start else 'undated',
            })
        sources_block = '\n'.join(
            f"[{s['n']}] {s['title']} — {s['source']}, {s['published']}. {s['url']}"
            for s in numbered_sources
        ) or 'No indexed news sources are available for this crisis.'

        # Real article substance for the top few sources — previously
        # fetched into `news` above but never actually used beyond a
        # title/date/url citation stub, even though News.content is a real
        # column populated at ingest. Without this, Claude had only
        # metadata to cite, not anything to expand a real explanation
        # from — the direct cause of "bland, severity-only" briefings.
        excerpt_parts = []
        for i, n in enumerate(news[:3], 1):
            if n.content:
                excerpt_parts.append(f"[{i}] {n.content[:600]}")
        # A live-scraped description of the crisis's own primary source
        # (not one of the indexed News rows) — same real-page-metadata
        # fetch already used elsewhere in this app for pin-location
        # refinement, reused here for its `description` field instead.
        source_media = None
        if crisis.source_url:
            meta = fetch_real_page_metadata(crisis.source_url)
            if meta and meta.get('description'):
                excerpt_parts.append(f"Primary source description: {meta['description']}")
            if meta and (meta.get('image_url') or meta.get('video_url')):
                source_media = {
                    'image_url': meta.get('image_url'),
                    'video_url': meta.get('video_url'),
                }
        excerpts_block = '\n\n'.join(excerpt_parts) or 'No real article text is available beyond the headlines above.'

        # Build context for Claude
        context = f"""
Crisis: {crisis.title}
Location: {crisis.country}
Type: {crisis.type}
Severity: {crisis.severity}/100
Confidence: {crisis.confidence}%
Source Reliability: {reliability['reliability']} ({reliability['source_count']} sources)

Analysis: {crisis.analysis}

Escalation Trend: {escalation['trend']}{f" (velocity: {escalation['velocity']} points/day)" if escalation.get('velocity') is not None else ""}
Economic Impact: {economic['impact_severity']}
Affected Sectors: {', '.join(economic['sectors_typically_exposed'])}
{f"Trade Openness: {economic['economic_profile']['trade_openness_percent_of_gdp']}% of GDP" if economic.get('economic_profile') else ""}

Numbered Source List (cite these by number — see instructions):
{sources_block}

Real article text/excerpts to draw the actual explanation from:
{excerpts_block}
"""

        # Fetch Wikipedia image (non-blocking, optional)
        image = fetch_wikipedia_image(crisis.country, crisis.title)

        # Call Claude API for briefing
        if anthropic_client and anthropic_client.api_key:
            try:
                message = anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2800,
                    messages=[
                        {
                            "role": "user",
                            "content": f"""Write a single, expansive, specific explanation of what is actually happening in this crisis, for a journalist or political commentator. Not a severity summary, not a generic category description — the real situation: who did what, to whom, when, where, and why it matters right now. Pull the real substance from the article excerpts and numbered sources below rather than speaking in generalities.

CITATION RULES (this will be published under this outlet's name, so sourcing discipline matters):
- Whenever you state a specific fact, figure, quote, or claim that comes from the numbered source list or the article excerpts below, cite it inline immediately after the claim using its bracketed number, e.g. "...forces reportedly withdrew from the eastern district [3]."
- A single sentence may carry multiple citations if it draws on more than one source, e.g. "[2][5]".
- Only cite numbers that appear in the provided source list. Never invent a source, a number, a quote, or a statistic that isn't backed by the list, the excerpts, or the structured Crisis Context data.
- Analytical judgment that comes from your own reasoning rather than a listed source should NOT carry a citation — present it plainly as analysis.
- If the source list and excerpts are thin, say so explicitly rather than filling the gap with an uncited "fact" — a shorter, honest explanation is better than a padded one.

Format your response as flowing prose — no section headers, no bullet points, just the explanation itself (do not add a "Sources" section yourself — one is appended automatically after your response).

Crisis Context:
{context}

Be specific — name actors, places, and figures rather than speaking in generalities. Write 400-700 words, scaled to how much real material is actually available above rather than padded to a fixed length."""
                        }
                    ]
                )

                briefing_text = message.content[0].text
                briefing_text += _format_sources_section(numbered_sources)
                result = {
                    'briefing': briefing_text,
                    'sources': numbered_sources,
                    'model': 'claude-3-5-sonnet-20241022',
                    'timestamp': datetime.utcnow().isoformat()
                }
                if image:
                    result['image'] = image
                if source_media:
                    result['source_media'] = source_media
                # Cache for 1 hour — briefings change slowly and each API call
                # costs real money. TTL 3600 means at most one Claude call per
                # crisis per hour across all concurrent users.
                cache_set(cache_key, result, ttl=3600)
                logger.info(f"[Briefing] Cached briefing for crisis {crisis_id} (TTL 3600s)")
                return result
            except Exception as e:
                logger.error(f"AI briefing error: {e}")
                return None
        else:
            logger.info("ANTHROPIC_API_KEY not set — generating static briefing")
            result = _generate_static_briefing(crisis, escalation, economic, reliability, numbered_sources, image, excerpt_parts, source_media)
            if result:
                cache_set(cache_key, result, ttl=3600)
            return result
    finally:
        session.close()


def _format_sources_section(numbered_sources):
    """Render a '## Sources' markdown section from our own structured news
    rows — never model-generated — so every link is real and the numbering
    matches exactly what the briefing (AI or static) was told to cite."""
    if not numbered_sources:
        return "\n\n## Sources\n*No indexed news sources were available for this crisis at generation time.*"
    lines = [
        f"{s['n']}. [{s['source']} — {s['title']}]({s['url']}) ({s['published']})"
        if s['url'] else f"{s['n']}. {s['source']} — {s['title']} ({s['published']})"
        for s in numbered_sources
    ]
    return "\n\n## Sources\n" + '\n'.join(lines)


def _generate_static_briefing(crisis, escalation, economic, reliability, numbered_sources, image, excerpt_parts=None, source_media=None):
    """Generate a rule-based, single-explanation briefing when no API key
    is available — built from real material (crisis.analysis, real article
    excerpts) rather than a severity-only template. Honest when that real
    material is thin: says so rather than padding with generic phrasing."""
    excerpt_parts = excerpt_parts or []
    sev = crisis.severity
    trend = escalation.get('trend', 'stable') if escalation else 'stable'
    velocity = escalation.get('velocity') if escalation else None
    velocity = velocity if velocity is not None else 0
    impact_sev = economic.get('impact_severity', 'moderate') if economic else 'moderate'
    sectors = ', '.join(economic.get('sectors_typically_exposed', [])) if economic else 'General Economy'
    src_count = reliability.get('source_count', 1) if reliability else 1
    rel_label = reliability.get('reliability', 'moderate') if reliability else 'moderate'
    has_citable_news = bool(numbered_sources)
    has_real_material = bool(crisis.analysis) or bool(excerpt_parts)

    trend_desc = {
        'escalating': f'rapidly escalating (velocity +{abs(velocity):.1f} pts/day)',
        'de-escalating': f'de-escalating (velocity −{abs(velocity):.1f} pts/day)',
        'stable': 'holding at current intensity',
        'volatile': 'volatile with unpredictable swings',
        'insufficient_data': 'too new to establish a trend',
    }.get(trend, 'evolving')

    # Lead with the real explanation when there's real material to draw
    # from (crisis.analysis, real article excerpts) — this is what makes
    # it an actual explanation instead of a severity summary. Falls back
    # to an honest, explicit "not enough real material" statement rather
    # than padding with generic type-based phrasing when there isn't any.
    if has_real_material:
        explanation_parts = []
        if crisis.analysis:
            # crisis.analysis for GDELT rows is always the fixed ingestion
            # template "GDELT-monitored event (CAMEO nnn), reported via
            # {source_url}" — pure restated metadata, not real narrative,
            # and the URL is already shown in EventAnalysis.tsx's SOURCE
            # section above this text. Strip that exact clause (for any
            # source, not just GDELT — the "reported via <url>" restatement
            # is redundant regardless of where it came from); keep whatever
            # real content remains, if any.
            cleaned_analysis = re.sub(
                r'\bGDELT-monitored event \(CAMEO \d+\),?\s*reported via \S+\s*',
                '',
                crisis.analysis,
            ).strip()
            if cleaned_analysis:
                explanation_parts.append(cleaned_analysis)
        for part in excerpt_parts:
            # part is already "[n] excerpt text" or "Primary source description: ..."
            explanation_parts.append(part if part.startswith('[') else part)
        real_explanation = ' '.join(explanation_parts) if explanation_parts else (
            "No additional real narrative is indexed for this crisis beyond what's "
            "shown above — treat the figures below as the only currently-grounded facts."
        )
    else:
        real_explanation = (
            f"No real article text or analysis is indexed for this crisis yet beyond its "
            f"structured classification — {crisis.type} activity in {crisis.country}. "
            f"This is a placeholder until real source material is available; treat the "
            f"figures below as the only currently-grounded facts."
        )

    # No restated actor/verb/severity/source-URL sentence here — severity is
    # already shown as its own badge in the UI, and crisis.source_url is
    # already shown in EventAnalysis.tsx's dedicated SOURCE section above
    # this text, so this leads with a plain, minimal line and goes straight
    # into the real analytical content instead.
    # No "[n]" citation marker here — that convention only makes sense next
    # to a real numbered '## Sources' list, which this static-fallback path
    # no longer appends (the one real source is already shown in
    # EventAnalysis.tsx's SOURCE section above this text). Point back to
    # that section in plain language instead of a dangling bracket number.
    corroboration_sentence = (
        "Recent indexed reporting corroborates this beyond the source cited above; "
        "every citation should be independently verified before publication."
        if has_citable_news
        else "No recent indexed reporting is available to corroborate developments beyond what's stated above."
    )
    briefing_text = f"""Global Severity: {sev}/100

This event is {trend_desc}. {real_explanation} {corroboration_sentence} Economic exposure is rated **{impact_sev}** across {sectors}; source reliability is **{rel_label}** across {src_count} tracked source(s), {crisis.confidence}% overall confidence."""

    # No appended '## Sources' block here — for this static-fallback path,
    # crisis.source_url is the only real citable source GDELT crises ever
    # have, and it's already surfaced by EventAnalysis.tsx's own SOURCE
    # section above the briefing text, so repeating it below would be pure
    # duplication. The underlying _format_sources_section machinery is left
    # untouched and still used by the AI-generated path above, which can
    # genuinely have several distinct indexed sources.

    result = {
        'briefing': briefing_text,
        'sources': numbered_sources,
        'model': 'static-rules',
        'timestamp': datetime.utcnow().isoformat()
    }
    if image:
        result['image'] = image
    if source_media:
        result['source_media'] = source_media
    return result
