"""What a watched place alerts about. One small JSON object per place (geointel_watch_places.alert_prefs):

    {"hazards": {"types": ["TC", "FL", "WF", "DR"], "min_level": "orange"}}

    {"weather": {"heat_c": 38, "rain_mm": 80}}
    {"situations": {"enabled": true, "min_severity": "serious", "statements": false}}

A missing "hazards" key means the default: every hazard type, at the account's minimum level. A missing "weather" key means
the place uses the account's forecast limits; a "weather" object (even an empty one) replaces them for this place. Everything
is validated here, on the server, before it is saved or used.
"""
HAZARD_TYPES = ('TC', 'FL', 'WF', 'DR')      # the live hazard feed: cyclones, floods, wildfires, droughts
LEVELS = ('green', 'orange', 'red')
SITUATION_SEVERITIES = ('serious', 'severe', 'critical')    # the app's own written scale: 40+, 60+, 80+


class InvalidPlaceAlertPrefs(ValueError):
    pass


def clean_prefs(value):
    """A validated prefs object (only the keys given), {} for none, or InvalidPlaceAlertPrefs."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidPlaceAlertPrefs('alert_prefs must be an object')
    unknown = set(value) - {'hazards', 'weather', 'situations'}
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
    if 'weather' in value:
        from services.condition_alerts import InvalidConditions, clean_conditions
        try:
            out['weather'] = clean_conditions(value['weather'])
        except InvalidConditions as e:
            raise InvalidPlaceAlertPrefs(str(e))
    if 'situations' in value:
        sit = value['situations']
        if not isinstance(sit, dict) or set(sit) - {'enabled', 'min_severity', 'statements'}:
            raise InvalidPlaceAlertPrefs('situations must be {"enabled": ..., "min_severity": ..., "statements": ...}')
        cleaned = {}
        for key in ('enabled', 'statements'):
            if key in sit:
                if not isinstance(sit[key], bool):
                    raise InvalidPlaceAlertPrefs(f'situations {key} must be true or false')
                cleaned[key] = sit[key]
        if 'min_severity' in sit:
            if sit['min_severity'] not in SITUATION_SEVERITIES:
                raise InvalidPlaceAlertPrefs(f"min_severity must be one of {', '.join(SITUATION_SEVERITIES)}")
            cleaned['min_severity'] = sit['min_severity']
        out['situations'] = cleaned
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


def weather_limits(prefs, account_conditions):
    """The forecast limits that apply to a place: its own when it has chosen some, else the account's."""
    own = (stored_prefs(prefs) or {}).get('weather')
    return dict(account_conditions) if own is None else dict(own)


def situation_settings(prefs):
    """(enabled, minimum severity score, include statements) for a place. Off unless the place switched it on."""
    sit = (stored_prefs(prefs) or {}).get('situations', {})
    floor = {'serious': 40, 'severe': 60, 'critical': 80}[sit.get('min_severity', 'serious')]
    return sit.get('enabled') is True, floor, sit.get('statements') is True
