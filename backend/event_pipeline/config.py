"""
Loader for config/event_filters.json — every tunable the pipeline uses
(keyword lists, thresholds, weights) lives there, the same code-free tuning
model config/source_reliability.json already uses.
"""
import json
import os

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'event_filters.json'
)

_config = None


def _strip_comments(value):
    """Drop '_comment'-style keys (anything starting with '_') at every level,
    so documentation inside the JSON never leaks into keyword lists."""
    if isinstance(value, dict):
        return {k: _strip_comments(v) for k, v in value.items() if not k.startswith('_')}
    if isinstance(value, list):
        return [_strip_comments(v) for v in value]
    return value


def get_config():
    """The parsed config, loaded once per process."""
    global _config
    if _config is None:
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            _config = _strip_comments(json.load(f))
    return _config


def reload_config():
    """Re-read the file (tests, or after editing thresholds in a running shell)."""
    global _config
    _config = None
    return get_config()
