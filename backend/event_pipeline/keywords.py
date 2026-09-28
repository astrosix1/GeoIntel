"""
Word-boundary keyword matching.

Ingestion used to test keywords with a plain substring check (`kw in text`),
which let 'ai' match "s-ai-d" (so ordinary quotes became technology
stories), 'war' match "soft-war-e", "to-war-ds" and "War-saw" (severity 80),
and 'oil'/'gas' match "soil"/"Vegas". Every keyword test in the pipeline goes
through here instead: whole words only, plus the common inflections
(-s/-es/-ed/-ing) so "strikes", "bombed" and "protesting" still count.
"""
import re
from functools import lru_cache

from .config import get_config

_SUFFIXES = r'(?:s|es|ed|ing)?'


def _pattern_for(keyword):
    # Internal whitespace in multi-word phrases matches any run of spaces.
    body = r'\s+'.join(re.escape(part) for part in keyword.lower().split())
    return body + _SUFFIXES


@lru_cache(maxsize=None)
def compile_keywords(keywords):
    """One compiled, case-insensitive alternation for a tuple of keywords.
    Longer phrases are tried first so 'peace deal' wins over 'peace'."""
    ordered = sorted(set(keywords), key=len, reverse=True)
    return re.compile(r'\b(?:' + '|'.join(_pattern_for(k) for k in ordered) + r')\b', re.IGNORECASE)


def find_keywords(text, keywords):
    """Every keyword from `keywords` that appears in `text` as a whole word
    (inflections allowed). Returns the keywords themselves, not the matched
    inflected forms, so callers can look up weights by keyword."""
    if not text or not keywords:
        return []
    return [k for k in keywords if compile_keywords((k,)).search(text)]


def has_keyword(text, keywords):
    if not text or not keywords:
        return False
    return compile_keywords(tuple(keywords)).search(text) is not None


@lru_cache(maxsize=1)
def _exclusion_pattern(phrases):
    if not phrases:
        return None
    return compile_keywords(phrases)


def strip_excluded_phrases(text):
    """Remove idioms that would otherwise trigger a crisis keyword ('heart
    attack', 'price war', 'strike a deal') before any matching runs."""
    if not text:
        return text or ''
    phrases = tuple(get_config().get('phrase_exclusions', {}).get('phrases', []))
    pattern = _exclusion_pattern(phrases)
    return pattern.sub(' ', text) if pattern else text
