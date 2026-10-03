"""Shared Anthropic client for AI-backed features (briefing, history, country
profile, scenarios, incident geocoding)."""
import os

# One place to change the model. Override per environment with ANTHROPIC_MODEL.
AI_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-5-5')

try:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except Exception:
    anthropic_client = None
