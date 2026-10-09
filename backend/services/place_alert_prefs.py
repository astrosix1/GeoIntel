"""What a watched place alerts about. One small JSON object per place (geointel_watch_places.alert_prefs):

    {"hazards": {"types": ["TC", "FL", "WF", "DR"], "min_level": "orange"}}

A missing key means the default: every hazard type, at the account's minimum level. Everything is validated here, on the
server, before it is saved or used.
"""
HAZARD_TYPES = ('TC', 'FL', 'WF', 'DR')      # the live hazard feed: cyclones, floods, wildfires, droughts
LEVELS = ('green', 'orange', 'red')


class InvalidPlaceAlertPrefs(ValueError):
    pass


def clean_prefs(value):
    """A validated prefs object (only the keys given), {} for none, or InvalidPlaceAlertPrefs."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidPlaceAlertPrefs('alert_prefs must be an object')
    unknown = set(value) - {'hazards'}
    if unknown:
        raise InvalidPlaceAlertPrefs(f"unknown alert choice: {sorted(unknown)[0]}")
    out = {}
    if 'hazards' in value:
        hazards = value['hazards']
        if not isinstance(hazards, dict) or set(hazards) - {'types', 'min_level'}:
            raise InvalidPlaceAlertPrefs('hazards must be {"types": [...], "min_level": ...}')
        cleaned = {}
        if 'types' in hazards:
            types = hazards['types']
            if not isinstance(types, list) or any(t not in HAZARD_TYPES for t in types):
                raise InvalidPlaceAlertPrefs(f"hazard types must come from {', '.join(HAZARD_TYPES)}")
            cleaned['types'] = [t for t in HAZARD_TYPES if t in types]     # fixed order, no repeats
        if 'min_level' in hazards:
            if hazards['min_level'] not in LEVELS:
                raise InvalidPlaceAlertPrefs(f"min_level must be one of {', '.join(LEVELS)}")
            cleaned['min_level'] = hazards['min_level']
        out['hazards'] = cleaned
    return out


def stored_prefs(raw):
    """Prefs read back from the database: anything that no longer validates counts as the defaults."""
    try:
        return clean_prefs(raw)
    except InvalidPlaceAlertPrefs:
        return {}


def hazard_settings(prefs, account_min_level):
    """(set of hazard types to alert on, minimum level) for a place, with defaults filled in."""
    hazards = (stored_prefs(prefs) or {}).get('hazards', {})
    return set(hazards.get('types', HAZARD_TYPES)), hazards.get('min_level') or account_min_level
