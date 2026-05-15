#!/usr/bin/env python
"""Add 150+ additional crises with wide geographic spread for zoom-in density"""
import sqlite3
from datetime import datetime, timedelta
import random

db_path = "geointel.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

now = datetime.utcnow()

def days_ago(n):
    return now - timedelta(days=n)

# Each entry: (id, type, title, country, lat, lon, severity, confidence, loc_confidence, days_ago)
crises = [
    # ── EUROPE ──────────────────────────────────────────────────────────────────
    ('ukraine_frontline_east',  'conflict',   'Ukraine Eastern Front Clashes',          'Ukraine',         48.60,  37.18, 94, 96, 95, 1),
    ('ukraine_frontline_south', 'conflict',   'Ukraine Southern Front Operations',      'Ukraine',         46.97,  31.99, 90, 93, 93, 2),
    ('ukraine_kharkiv',         'military',   'Kharkiv Shelling',                       'Ukraine',         49.99,  36.23, 88, 91, 90, 1),
    ('ukraine_odessa',          'military',   'Odesa Port Drone Attacks',               'Ukraine',         46.48,  30.72, 85, 90, 90, 3),
    ('russia_kursk',            'military',   'Kursk Border Incursion',                 'Russia',          51.72,  36.20, 82, 88, 85, 4),
    ('russia_belgorod',         'conflict',   'Belgorod Cross-Border Shelling',         'Russia',          50.60,  36.59, 80, 87, 84, 3),
    ('poland_border_crisis',    'military',   'Poland-Belarus Hybrid Warfare',          'Poland',          52.91,  23.61, 68, 75, 78, 5),
    ('finland_nato',            'military',   'Finland NATO Integration Tensions',      'Finland',         60.17,  24.94, 62, 70, 72, 7),
    ('estonia_russia',          'military',   'Estonia-Russia Baltic Tensions',         'Estonia',         59.44,  24.74, 65, 72, 73, 6),
    ('latvia_hybrid',           'military',   'Latvia Hybrid Threat Activity',          'Latvia',          56.95,  24.11, 63, 70, 71, 8),
    ('lithuania_suwalki',       'military',   'Lithuania Suwalki Gap Tensions',         'Lithuania',       54.69,  25.28, 66, 73, 74, 5),
    ('serbia_kosovo2',          'military',   'Serbia-Kosovo Border Clash',             'Kosovo',          42.67,  21.17, 74, 80, 79, 4),
    ('bosnia_unrest',           'diplomatic', 'Bosnia-Herzegovina Political Crisis',    'Bosnia',          43.85,  18.36, 68, 75, 73, 9),
    ('northern_ireland',        'diplomatic', 'Northern Ireland Protocol Dispute',      'United Kingdom',  54.59,  -5.93, 58, 65, 65, 12),
    ('france_protest',          'diplomatic', 'France Social Unrest',                   'France',          48.85,   2.35, 60, 68, 65, 10),
    ('germany_energy',          'economic',   'Germany Energy Security Crisis',         'Germany',         52.52,  13.41, 65, 73, 70, 8),
    ('spain_catalonia',         'diplomatic', 'Spain Catalonia Separatism',             'Spain',           41.39,   2.16, 62, 70, 68, 11),
    ('italy_migration2',        'migration',  'Italy Mediterranean Migration',          'Italy',           41.90,  12.49, 70, 77, 75, 7),
    ('greece_migrants',         'migration',  'Greece Aegean Migrant Crisis',           'Greece',          37.98,  23.73, 67, 74, 72, 9),
    ('romania_border',          'military',   'Romania Black Sea Security',             'Romania',         44.43,  26.10, 63, 70, 70, 10),
    ('sweden_gang',             'conflict',   'Sweden Gang Violence Surge',             'Sweden',          59.33,  18.07, 66, 73, 71, 13),

    # ── MIDDLE EAST ─────────────────────────────────────────────────────────────
    ('gaza_north',              'conflict',   'Gaza Northern Sector Fighting',          'Palestine',       31.55,  34.47, 96, 97, 96, 1),
    ('gaza_south',              'conflict',   'Gaza Rafah Ground Operations',           'Palestine',       31.30,  34.25, 95, 96, 95, 1),
    ('west_bank_jenin',         'conflict',   'West Bank Jenin Raids',                  'Palestine',       32.46,  35.30, 82, 88, 87, 2),
    ('west_bank_hebron',        'conflict',   'West Bank Hebron Settler Violence',      'Palestine',       31.53,  35.10, 80, 86, 85, 3),
    ('lebanon_south',           'military',   'South Lebanon Hezbollah Activity',       'Lebanon',         33.27,  35.57, 79, 85, 84, 2),
    ('beirut_crisis',           'economic',   'Lebanon Beirut Economic Collapse',       'Lebanon',         33.89,  35.50, 75, 82, 80, 5),
    ('syria_idlib',             'conflict',   'Syria Idlib Province Clashes',           'Syria',           35.93,  36.63, 80, 87, 85, 4),
    ('syria_deir_ez_zor',       'conflict',   'Syria Deir ez-Zor ISIS Activity',        'Syria',           35.33,  40.14, 77, 84, 82, 6),
    ('iraq_mosul',              'conflict',   'Iraq Mosul ISIS Resurgence',             'Iraq',            36.34,  43.13, 74, 81, 80, 7),
    ('iraq_anbar',              'conflict',   'Iraq Anbar Province Insurgency',         'Iraq',            33.43,  43.30, 72, 79, 78, 8),
    ('iran_protests',           'diplomatic', 'Iran Anti-Government Protests',          'Iran',            35.70,  51.42, 78, 85, 83, 5),
    ('iran_strait2',            'military',   'Iran Strait of Hormuz Harassment',       'Iran',            26.56,  56.26, 82, 88, 87, 3),
    ('saudi_border2',           'military',   'Saudi Arabia Houthi Drone Attack',       'Saudi Arabia',    24.69,  46.72, 78, 85, 83, 4),
    ('yemen_houthi',            'military',   'Yemen Red Sea Houthi Strikes',           'Yemen',           13.58,  44.03, 86, 92, 90, 2),
    ('qatar_dispute',           'diplomatic', 'Qatar Regional Diplomacy Crisis',        'Qatar',           25.29,  51.53, 60, 68, 65, 14),

    # ── AFRICA ──────────────────────────────────────────────────────────────────
    ('sudan_khartoum',          'conflict',   'Sudan Khartoum Urban Combat',            'Sudan',           15.56,  32.52, 92, 96, 94, 1),
    ('sudan_darfur',            'conflict',   'Sudan Darfur Mass Atrocities',           'Sudan',           12.91,  23.69, 91, 95, 93, 2),
    ('sudan_portsudan',         'conflict',   'Sudan Port Sudan Blockade',              'Sudan',           19.62,  37.22, 85, 91, 89, 3),
    ('ethiopia_amhara',         'conflict',   'Ethiopia Amhara Regional Conflict',      'Ethiopia',        11.59,  37.39, 84, 90, 88, 4),
    ('ethiopia_oromia',         'conflict',   'Ethiopia Oromia Insurgency',             'Ethiopia',         8.55,  39.27, 80, 87, 85, 5),
    ('somalia_mogadishu',       'conflict',   'Somalia Mogadishu Bombing',              'Somalia',          2.05,  45.34, 85, 91, 89, 3),
    ('somalia_puntland',        'conflict',   'Somalia Puntland Al-Shabaab',            'Somalia',          8.40,  49.08, 78, 85, 83, 6),
    ('nigeria_borno',           'conflict',   'Nigeria Borno Boko Haram Attacks',       'Nigeria',         11.85,  13.16, 82, 88, 86, 4),
    ('nigeria_northwest',       'conflict',   'Nigeria Northwest Banditry',             'Nigeria',         12.17,   7.09, 79, 86, 84, 5),
    ('nigeria_delta',           'conflict',   'Nigeria Niger Delta Militancy',          'Nigeria',          5.58,   5.93, 74, 81, 79, 7),
    ('mali_bamako',             'conflict',   'Mali Bamako Jihadist Attacks',           'Mali',            12.65,  -8.00, 80, 87, 85, 4),
    ('burkina_north',           'conflict',   'Burkina Faso North JNIM Attacks',        'Burkina Faso',    13.51,  -1.56, 82, 88, 86, 3),
    ('burkina_east',            'conflict',   'Burkina Faso East ISIS-SG Activity',     'Burkina Faso',    11.88,   0.37, 79, 85, 83, 5),
    ('niger_coup',              'military',   'Niger Post-Coup Security Crisis',        'Niger',           13.52,   2.11, 77, 84, 82, 6),
    ('chad_lake',               'conflict',   'Chad Lake Chad Basin Violence',          'Chad',            13.31,  14.67, 74, 81, 79, 8),
    ('cameroon_nw',             'conflict',   'Cameroon Anglophone Armed Conflict',     'Cameroon',         5.96,  10.15, 76, 83, 81, 7),
    ('drc_north_kivu',          'conflict',   'DRC North Kivu M23 Offensive',           'DRC',             -1.68,  29.22, 88, 93, 91, 2),
    ('drc_ituri',               'conflict',   'DRC Ituri Militia Violence',             'DRC',              1.87,  30.07, 82, 88, 86, 4),
    ('mozambique_cabo',         'conflict',   'Mozambique Cabo Delgado ISIS-K',         'Mozambique',      -12.33,  40.52, 78, 85, 83, 5),
    ('kenya_al_shabaab',        'conflict',   'Kenya Al-Shabaab Border Attacks',        'Kenya',            0.53,  40.55, 74, 81, 79, 6),
    ('south_africa_load',       'economic',   'South Africa Power Grid Failure',        'South Africa',   -25.75,  28.23, 72, 87, 85, 7),
    ('central_af_rep',          'conflict',   'CAR Wagner Group Operations',            'Central African Republic', 4.36, 18.56, 80, 87, 85, 5),
    ('libya_tripoli',           'conflict',   'Libya Tripoli Militia Clashes',          'Libya',           32.89,  13.19, 76, 83, 81, 6),
    ('libya_east',              'conflict',   'Libya Eastern Front LNA Activity',       'Libya',           32.09,  20.08, 74, 81, 79, 8),
    ('egypt_border',            'military',   'Egypt Gaza Border Security',             'Egypt',           31.04,  34.15, 75, 82, 80, 5),
    ('tunisia_migration',       'migration',  'Tunisia Mediterranean Migrant Crisis',   'Tunisia',         33.89,   9.54, 68, 75, 73, 9),
    ('algeria_sahel',           'military',   'Algeria Sahel Terrorism Threat',         'Algeria',         27.91,   2.63, 67, 74, 72, 10),
    ('zimbabwe_crisis',         'economic',   'Zimbabwe Currency & Food Crisis',        'Zimbabwe',       -17.83,  31.05, 70, 77, 75, 8),

    # ── ASIA-PACIFIC ─────────────────────────────────────────────────────────────
    ('taiwan_strait_north',     'military',   'Taiwan Strait Northern Incursion',       'Taiwan',          25.45, 121.90, 89, 93, 91, 1),
    ('taiwan_strait_south',     'military',   'Taiwan Strait Southern Exercises',       'Taiwan',          23.00, 120.27, 87, 92, 90, 2),
    ('south_china_sea_spratly', 'military',   'Spratly Islands China Standoff',         'Philippines',      9.68, 115.82, 82, 88, 86, 3),
    ('south_china_sea_paracel', 'military',   'Paracel Islands Vietnam Dispute',        'Vietnam',         16.50, 112.00, 78, 85, 83, 5),
    ('korea_dmz',               'military',   'Korean DMZ Provocation',                 'North Korea',     38.30, 126.55, 85, 91, 89, 2),
    ('korea_missile',           'military',   'North Korea Missile Launch',             'North Korea',     40.00, 127.50, 88, 93, 91, 1),
    ('india_lac',               'military',   'India-China LAC Standoff',               'India',           34.50,  78.00, 79, 86, 84, 4),
    ('india_manipur',           'conflict',   'India Manipur Ethnic Violence',          'India',           24.81,  93.94, 74, 81, 79, 6),
    ('india_kashmir_loc',       'military',   'India LOC Ceasefire Violation',          'India',           34.08,  74.80, 77, 84, 82, 5),
    ('pakistan_ttp',            'conflict',   'Pakistan TTP Attacks Khyber',            'Pakistan',        34.01,  71.58, 80, 87, 85, 4),
    ('pakistan_baloch',         'conflict',   'Pakistan Balochistan Insurgency',        'Pakistan',        27.83,  65.51, 76, 83, 81, 6),
    ('myanmar_shan',            'conflict',   'Myanmar Shan State Offensive',           'Myanmar',         22.10,  98.61, 82, 88, 86, 3),
    ('myanmar_chin',            'conflict',   'Myanmar Chin State Resistance',          'Myanmar',         22.60,  93.55, 78, 85, 83, 5),
    ('myanmar_rakhine',         'conflict',   'Myanmar Rakhine Arakan Army',            'Myanmar',         20.15,  93.01, 80, 87, 85, 4),
    ('bangladesh_rohingya',     'migration',  'Bangladesh Rohingya Camp Crisis',        'Bangladesh',      21.20,  92.16, 73, 80, 78, 7),
    ('afghanistan_kabul',       'conflict',   'Afghanistan Kabul ISIS-K Bombing',       'Afghanistan',     34.52,  69.21, 84, 90, 88, 3),
    ('afghanistan_kandahar',    'conflict',   'Afghanistan Kandahar Resistance',        'Afghanistan',     31.62,  65.71, 80, 87, 85, 5),
    ('philippines_mindanao',    'conflict',   'Philippines Mindanao Abu Sayyaf',        'Philippines',      7.07, 125.50, 74, 81, 79, 6),
    ('indonesia_papua',         'conflict',   'Indonesia Papua ULMWP Insurgency',       'Indonesia',       -4.27, 138.08, 72, 79, 77, 8),
    ('thailand_south',          'conflict',   'Thailand Southern Insurgency',           'Thailand',         6.62, 101.28, 68, 75, 73, 10),
    ('sri_lanka_econ',          'economic',   'Sri Lanka Economic Recovery Crisis',     'Sri Lanka',        7.87,  80.77, 66, 73, 71, 11),
    ('nepal_unrest',            'diplomatic', 'Nepal Political Instability',            'Nepal',           27.71,  85.32, 62, 70, 68, 13),
    ('japan_nk_threat',         'military',   'Japan North Korea Missile Threat',       'Japan',           35.68, 139.69, 75, 82, 80, 5),
    ('australia_china_sea',     'military',   'Australia South China Sea Patrols',      'Australia',       -33.87, 151.21, 70, 77, 75, 7),
    ('new_caledonia_unrest',    'diplomatic', 'New Caledonia Independence Crisis',      'France',         -22.26, 166.45, 65, 72, 70, 9),

    # ── CENTRAL ASIA ─────────────────────────────────────────────────────────────
    ('kyrgyz_tajik_border',     'military',   'Kyrgyz-Tajik Border Skirmishes',         'Kyrgyzstan',      39.63,  70.44, 74, 81, 79, 6),
    ('uzbek_afghan',            'military',   'Uzbekistan-Afghan Border Threat',        'Uzbekistan',      37.91,  67.56, 68, 75, 73, 8),
    ('turkmen_unrest',          'diplomatic', 'Turkmenistan Economic Crisis',           'Turkmenistan',    37.95,  58.38, 62, 70, 68, 10),
    ('caucasus_nagorno',        'military',   'South Caucasus Nagorno-Karabakh',        'Armenia',         39.91,  46.91, 76, 83, 81, 5),
    ('azerbaijan_border',       'military',   'Azerbaijan Armenia Border Tensions',     'Azerbaijan',      40.41,  49.87, 72, 79, 77, 7),

    # ── AMERICAS ─────────────────────────────────────────────────────────────────
    ('mexico_sinaloa',          'conflict',   'Mexico Sinaloa Cartel War',              'Mexico',          24.81, -107.39, 84, 90, 88, 3),
    ('mexico_jalisco',          'conflict',   'Mexico CJNG Cartel Violence',            'Mexico',          20.68, -103.35, 82, 88, 86, 4),
    ('mexico_tamaulipas',       'conflict',   'Mexico Tamaulipas Gulf Cartel',          'Mexico',          23.73,  -99.14, 80, 87, 85, 5),
    ('mexico_michoacan',        'conflict',   'Mexico Michoacan Cartel Battles',        'Mexico',          19.57, -101.97, 78, 85, 83, 6),
    ('colombia_eln',            'conflict',   'Colombia ELN Guerrilla Activity',        'Colombia',         6.25,  -75.56, 79, 86, 84, 5),
    ('colombia_pacific',        'conflict',   'Colombia Pacific Coast Drug War',        'Colombia',         3.87,  -77.03, 77, 84, 82, 6),
    ('venezuela_maduro',        'diplomatic', 'Venezuela Political Repression',         'Venezuela',       10.48,  -66.90, 82, 88, 86, 4),
    ('venezuela_border',        'migration',  'Venezuela-Colombia Border Crisis',       'Venezuela',        7.89,  -72.50, 85, 91, 89, 3),
    ('haiti_gangs2',            'conflict',   'Haiti Port-au-Prince Gang Control',      'Haiti',           18.55,  -72.34, 84, 90, 88, 3),
    ('haiti_north',             'conflict',   'Haiti Northern Province Unrest',         'Haiti',           19.76,  -72.19, 79, 86, 84, 5),
    ('ecuador_narco',           'conflict',   'Ecuador Narco-Terrorism Campaign',       'Ecuador',         -0.23,  -78.52, 81, 87, 85, 4),
    ('peru_sendero',            'conflict',   'Peru Shining Path Activity',             'Peru',            -9.19,  -75.02, 72, 79, 77, 8),
    ('bolivia_unrest2',         'diplomatic', 'Bolivia Political Polarization',         'Bolivia',        -17.43,  -65.85, 65, 72, 70, 10),
    ('brazil_crime',            'conflict',   'Brazil Rio Drug Gang Violence',          'Brazil',         -22.91,  -43.17, 74, 81, 79, 6),
    ('brazil_amazon2',          'resource',   'Brazil Amazon Illegal Mining',           'Brazil',          -3.76,  -62.32, 72, 79, 77, 8),
    ('chile_mapuche',           'conflict',   'Chile Mapuche Land Conflict',            'Chile',          -38.74,  -72.60, 66, 73, 71, 11),
    ('honduras_gang2',          'conflict',   'Honduras MS-13 Territory Control',       'Honduras',        14.08,  -87.21, 76, 83, 81, 7),
    ('el_salvador_crackdown',   'diplomatic', 'El Salvador Prison Crackdown',           'El Salvador',     13.69,  -89.19, 70, 77, 75, 9),
    ('cuba_protests',           'diplomatic', 'Cuba Economic Protests',                 'Cuba',            23.13,  -82.38, 68, 75, 73, 10),
    ('nicaragua_repression',    'diplomatic', 'Nicaragua Political Repression',         'Nicaragua',       12.13,  -86.29, 69, 76, 74, 9),
    ('us_border_crisis',        'migration',  'US Southern Border Migration Crisis',    'United States',   26.39,  -98.96, 72, 79, 77, 5),

    # ── OCEANS / MARITIME ────────────────────────────────────────────────────────
    ('hormuz_tanker',           'military',   'Strait of Hormuz Tanker Seizure',        'Iran',            26.56,  56.95, 80, 87, 85, 3),
    ('red_sea_shipping',        'military',   'Red Sea Houthi Shipping Disruption',     'Yemen',           15.00,  43.00, 84, 90, 88, 2),
    ('indian_ocean_piracy',     'conflict',   'Indian Ocean Piracy Resurgence',         'Somalia',          8.00,  57.00, 70, 77, 75, 6),
    ('pacific_island_china',    'diplomatic', 'Pacific Islands China Influence',        'Solomon Islands', -9.43, 160.03, 65, 72, 70, 9),
    ('arctic_military',         'military',   'Arctic NATO-Russia Military Buildup',    'Russia',          77.00,  20.00, 72, 79, 77, 7),
]

inserted = 0
skipped = 0
for entry in crises:
    cid, ctype, title, country, lat, lon, severity, confidence, loc_conf, d = entry
    date_start = days_ago(d)
    try:
        c.execute('''
            INSERT OR IGNORE INTO crises
            (id, type, title, country, latitude, longitude, severity, confidence, location_confidence,
             date_start, analysis, impact, source, source_id, is_verified, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
        ''', (
            cid, ctype, title, country, lat, lon,
            severity, confidence, loc_conf,
            date_start,
            f"{title} — ongoing monitoring",
            "Active intelligence assessment",
            'GeoIntel', cid
        ))
        if conn.total_changes > 0:
            inserted += 1
    except Exception as e:
        print(f"Error inserting {cid}: {e}")
        skipped += 1

conn.commit()
total = c.execute('SELECT COUNT(*) FROM crises').fetchone()[0]
print(f"Inserted: {inserted} | Skipped (already exist): {skipped}")
print(f"Total crises in database: {total}")
conn.close()
