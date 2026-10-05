"""Shared Anthropic client for AI-backed features (briefing, history, country
profile, scenarios, incident geocoding)."""
import os

# One place to change the model. Override per environment with ANTHROPIC_MODEL.
AI_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-5-5')

# Small, cheap model for tiny extraction jobs (picking a place name out of a
# headline). Override with ANTHROPIC_LOCATION_MODEL.
AI_LOCATION_MODEL = os.getenv('ANTHROPIC_LOCATION_MODEL', 'claude-haiku-4-5-20251001')

# Judges whether two borderline headlines are the same story (see services/stories.py).
AI_MERGE_MODEL = os.getenv('ANTHROPIC_MERGE_MODEL', AI_LOCATION_MODEL)

# Reads one article and records the place, casualty counts and scale cues (see
# services/story_facts.py). Override with ANTHROPIC_FACTS_MODEL.
AI_FACTS_MODEL = os.getenv('ANTHROPIC_FACTS_MODEL', AI_LOCATION_MODEL)

try:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except Exception:
    anthropic_client = None
