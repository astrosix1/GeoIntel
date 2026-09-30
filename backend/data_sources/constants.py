# A handful of actor ids in init_actors() aren't real ISO/World Bank country
# codes (EU is an aggregate, NK's real ISO/WB code is KP) — this translates
# those before querying WorldBank or matching an Actor to its EconomicData
# row. Every other actor id already is a real WB/ISO alpha-2 code.
ACTOR_WB_COUNTRY_OVERRIDES = {
    'NK': 'KP',
    'EU': 'EUU',
}

# Crisis type classifications
CRISIS_TYPES = {
    'conflict':       'Active Conflict',
    'military':       'Military Buildup',
    'diplomatic':     'Diplomatic Crisis',
    'economic':       'Economic Shock',
    'resource':       'Resource Conflict',
    'alliance':       'Alliance Shift',
    'proxy':          'Proxy Conflict',
    'technology':     'Tech War',
    'cyber':          'Cyber Attack',
    'infrastructure': 'Infrastructure Attack',
    'migration':      'Migration Crisis',
    'trade_war':      'Trade War',
    'bioweapon':      'Bioweapon Alert',
    'orbital':        'Orbital Conflict',
}
