"""
Tests for _parse_analogy_line() in app.py.

The historical-analogy match used to ask the model for a 0-100 "% match"
integer with no real precedent database or similarity metric behind it —
a fabricated precision. It now asks for a qualitative strength word
(strong/moderate/loose) instead, returned as `strength` (not `pct`) so
nothing downstream can mistake it for a percentage again.
"""


def test_valid_strong_analogy_line(app_module):
    text = "Some analysis text.\nANALOGY_MATCH: Cuban Missile Crisis|strong|Direct nuclear brinkmanship parallel."
    analogy, cleaned = app_module._parse_analogy_line(text)
    assert analogy == {
        'match': 'Cuban Missile Crisis',
        'strength': 'strong',
        'desc': 'Direct nuclear brinkmanship parallel.',
    }
    assert 'ANALOGY_MATCH' not in cleaned


def test_strength_is_case_insensitive(app_module):
    text = "ANALOGY_MATCH: Berlin Blockade|MODERATE|Some reason."
    analogy, _ = app_module._parse_analogy_line(text)
    assert analogy['strength'] == 'moderate'


def test_numeric_percentage_is_rejected(app_module):
    # The old format — a bare integer where a strength word now belongs —
    # must not silently pass through as some coerced value.
    text = "ANALOGY_MATCH: Some Crisis|87|Some reason."
    analogy, cleaned = app_module._parse_analogy_line(text)
    assert analogy is None
    assert 'ANALOGY_MATCH' not in cleaned


def test_unrecognized_strength_word_is_rejected(app_module):
    text = "ANALOGY_MATCH: Some Crisis|extreme|Some reason."
    analogy, _ = app_module._parse_analogy_line(text)
    assert analogy is None


def test_missing_analogy_line_returns_none_and_original_text(app_module):
    text = "Just some prose with no analogy line at all."
    analogy, cleaned = app_module._parse_analogy_line(text)
    assert analogy is None
    assert cleaned == text


def test_malformed_line_missing_pipe_segments(app_module):
    text = "ANALOGY_MATCH: Only one segment"
    analogy, _ = app_module._parse_analogy_line(text)
    assert analogy is None
