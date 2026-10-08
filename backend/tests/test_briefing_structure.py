"""Validation of the structured briefing (services/briefing_structure.py)."""
from services.briefing_structure import validate, as_text


def test_keeps_real_citations_and_drops_invented_ones():
    out = validate({'summary': 'S', 'key_points': [{'text': 'A', 'sources': [2, 9, 0, True, 2]}, {'text': 'B', 'sources': []}],
                    'unknowns': ['No casualty figure given']}, 3)
    assert out['key_points'][0]['sources'] == [2]
    assert out['key_points'][1]['sources'] == []


def test_caps_and_cleans():
    pts = [{'text': f'p{i}', 'sources': [1]} for i in range(9)]
    out = validate({'summary': ' a  b ', 'key_points': pts, 'unknowns': ['x', '', 'y', 'z', 'w']}, 1)
    assert out['summary'] == 'a b' and len(out['key_points']) == 5 and out['unknowns'] == ['x', 'y', 'z']


def test_unusable_is_none():
    assert validate(None, 1) is None
    assert validate({'summary': 'S', 'key_points': []}, 1) is None
    assert validate({'summary': '', 'key_points': [{'text': 'A', 'sources': []}]}, 1) is None


def test_text_form():
    t = as_text({'summary': 'S', 'key_points': [{'text': 'A', 'sources': [1, 2]}], 'unknowns': ['U']})
    assert '- A [1] [2]' in t and 'Not reported: U' in t
