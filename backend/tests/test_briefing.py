"""
Tests for the static-fallback briefing text shape (services/briefing.py,
_generate_static_briefing) — item 10.7 of the Phase 10 plan. The test env
runs with ANTHROPIC_API_KEY='' (see conftest.py), so generate_ai_briefing
always takes the static path here, exactly like production without a key
configured.

Covers: the new minimal `Global Severity: N/100` lead-in replacing the old
restated actor/verb/severity/source-URL sentence, and the removal of the
appended '## Sources' block from this specific static-fallback path (the
AI-generated path's own use of _format_sources_section is untouched and
not exercised by these tests).
"""
import pytest
from unittest.mock import patch

from models import Crisis
from cache import cache_delete
from services.briefing import generate_ai_briefing


@pytest.fixture(autouse=True)
def clean_crises(db_session):
    db_session.query(Crisis).delete()
    db_session.commit()
    # Every test in this file reuses id='brief-1' — generate_ai_briefing
    # caches its result by crisis_id, so without clearing it a later test
    # can silently be served an earlier test's cached (and differently-
    # seeded) result instead of actually exercising its own scenario.
    cache_delete('briefing:brief-1')
    yield
    db_session.query(Crisis).delete()
    db_session.commit()
    cache_delete('briefing:brief-1')


def seed_crisis(db_session, **overrides):
    defaults = dict(
        id='brief-1', type='conflict', title='Seoul criticizes Ukrainian',
        country='North Korea', latitude=0, longitude=0, severity=20,
        confidence=60, analysis='GDELT-monitored event (CAMEO 112), reported via https://example.com/a',
        source='GDELT', source_url='https://example.com/a',
    )
    defaults.update(overrides)
    db_session.add(Crisis(**defaults))
    db_session.commit()


def _patched(**kwargs):
    """Patch the escalation/economic/reliability/media calls
    generate_ai_briefing makes, so tests don't depend on real network
    calls or other real data rows existing."""
    base = dict(
        escalation={'trend': 'stable', 'velocity': None},
        economic={'impact_severity': 'moderate', 'sectors_typically_exposed': ['General Economy']},
        reliability={'reliability': 'moderate', 'source_count': 1},
        fetch_real_page_metadata=None,
        fetch_wikipedia_image=None,
    )
    base.update(kwargs)
    return base


def _run(crisis_id, **overrides):
    p = _patched(**overrides)
    with patch('services.briefing.analyze_escalation', return_value=p['escalation']), \
         patch('services.briefing.get_economic_impact', return_value=p['economic']), \
         patch('services.briefing.calculate_source_reliability', return_value=p['reliability']), \
         patch('services.briefing.fetch_real_page_metadata', return_value=p['fetch_real_page_metadata']), \
         patch('services.briefing.fetch_wikipedia_image', return_value=p['fetch_wikipedia_image']):
        return generate_ai_briefing(crisis_id)


def test_static_briefing_leads_with_plain_global_severity_line(app_module, db_session):
    seed_crisis(db_session, severity=20)
    result = _run('brief-1')
    assert result is not None
    assert result['model'] == 'static-rules'
    assert result['briefing'].startswith('Global Severity: 20/100')


def test_static_briefing_does_not_restate_actor_verb_or_source_url(app_module, db_session):
    seed_crisis(db_session, title='Seoul criticizes Ukrainian', source_url='https://example.com/a')
    result = _run('brief-1')
    briefing = result['briefing']
    # The old restated sentence embedded the title itself, e.g.
    # "Seoul criticizes Ukrainian (North Korea) is rated **Low** at
    # severity ...". That exact restatement should be gone — the title
    # can no longer precede "is rated" the way it used to.
    assert 'Seoul criticizes Ukrainian (North Korea) is rated' not in briefing
    assert 'Seoul criticizes Ukrainian (North Korea)' not in briefing


def test_static_briefing_has_no_sources_section(app_module, db_session):
    seed_crisis(db_session)
    result = _run('brief-1')
    assert '## Sources' not in result['briefing']


def test_static_briefing_strips_the_gdelt_ingestion_boilerplate(app_module, db_session):
    # crisis.analysis for GDELT rows is always this exact fixed template —
    # pure restated metadata (CAMEO code + the source_url, which is already
    # shown separately in EventAnalysis.tsx's SOURCE section), not real
    # narrative. The user explicitly called this out as part of what should
    # be gone, not just the old opening sentence.
    seed_crisis(db_session, analysis='GDELT-monitored event (CAMEO 112), reported via https://example.com/a')
    result = _run('brief-1')
    assert 'GDELT-monitored event' not in result['briefing']
    assert 'CAMEO 112' not in result['briefing']
    assert 'https://example.com/a' not in result['briefing']


def test_static_briefing_preserves_real_non_boilerplate_analysis(app_module, db_session):
    # A genuinely real, non-templated analysis string (e.g. from a
    # non-GDELT source) should still flow through untouched — only the
    # specific GDELT boilerplate clause is stripped, not real content.
    seed_crisis(db_session, source='ACLED', analysis='Armed clash between two factions near the border, per ACLED coding.')
    result = _run('brief-1')
    assert 'Armed clash between two factions near the border' in result['briefing']


def test_static_briefing_has_no_dangling_citation_marker(app_module, db_session):
    # Previously "...cited below[1]..." referenced a numbered '## Sources'
    # list that no longer exists on this path — the bracket number must not
    # appear with nothing for it to point to.
    seed_crisis(db_session)
    result = _run('brief-1', fetch_real_page_metadata={'title': 'A real headline', 'description': 'desc'})
    assert '[1]' not in result['briefing']
