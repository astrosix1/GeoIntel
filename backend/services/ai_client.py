"""Shared Anthropic client for AI-backed features (briefing, history)."""
import os

try:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except Exception:
    anthropic_client = None
