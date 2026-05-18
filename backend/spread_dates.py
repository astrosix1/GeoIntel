"""
Backdate crises across 2020-2026 so the timeline slider shows different events
for different years. Uses keyword matching for historically-dated events,
then distributes the rest evenly across the remaining years.
"""
import sqlite3, random, datetime, re

DB = "geointel.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

crises = c.execute("SELECT id, title, country FROM crises").fetchall()

def keyword_year(title, country):
    t = title.lower()
    co = country.lower()
    # ── 2020 ──────────────────────────────────────────────────────────────
    if any(k in t for k in ['covid','pandemic','nagorno','karabakh','tigray','belarus protest',
                             'george floyd','lebanese','beirut explosion','locust']):
        return 2020
    if co in ('ethiopia','armenia','azerbaijan','belarus','lebanon') and '2020' not in t:
        return 2020
    # ── 2021 ──────────────────────────────────────────────────────────────
    if any(k in t for k in ['taliban','kabul','myanmar coup','coup','haiti president',
                             'suez canal blocked','ransomware','colonial pipeline']):
        return 2021
    if co in ('afghanistan','myanmar','haiti') and 'coup' in t:
        return 2021
    # ── 2022 ──────────────────────────────────────────────────────────────
    if any(k in t for k in ['ukraine','russia invad','kharkiv','kherson','mariupol',
                             'kyiv','donbas','donetsk','luhansk','zaporizhzhia',
                             'odesa','kursk','frontline','annexation']):
        return 2022
    if co == 'ukraine':
        return 2022
    # ── 2023 ──────────────────────────────────────────────────────────────
    if any(k in t for k in ['gaza','hamas','october 7','al-aqsa flood','west bank',
                             'israel','rafah','khartoum','sudanese civil','rsf',
                             'prigozhin','wagner mutiny','niger coup','maui']):
        return 2023
    if co in ('sudan','niger','mali') and 'coup' in t:
        return 2023
    if co in ('israel','palestine','gaza') :
        return 2023
    # ── 2024 ──────────────────────────────────────────────────────────────
    if any(k in t for k in ['haiti gang','red sea attack','houthi','bab el-mandeb',
                             'taiwan election','georgia protest','senegal election',
                             'venezuela election','bangladesh protest','south korea']):
        return 2024
    if co in ('haiti','yemen') and 'houthi' in t:
        return 2024
    # ── 2025 ──────────────────────────────────────────────────────────────
    if any(k in t for k in ['trump tariff','nato expansion','arctic tension',
                             'ai weapon','space militari','horn of africa']):
        return 2025
    return None

# Assign keyword-based years first
assignments = {}
for (cid, title, country) in crises:
    yr = keyword_year(title, country)
    if yr:
        assignments[cid] = yr

# Spread remaining crises evenly across 2020-2026
YEAR_TARGETS = {2020: 8, 2021: 12, 2022: 18, 2023: 28, 2024: 55, 2025: 55, 2026: 48}
unassigned = [cid for (cid, _, _) in crises if cid not in assignments]
random.seed(42)
random.shuffle(unassigned)

year_counts = {yr: sum(1 for v in assignments.values() if v == yr) for yr in YEAR_TARGETS}

for cid in unassigned:
    # Pick the year most under its target
    best_yr = min(YEAR_TARGETS, key=lambda y: year_counts.get(y, 0) - YEAR_TARGETS[y])
    assignments[cid] = best_yr
    year_counts[best_yr] = year_counts.get(best_yr, 0) + 1

# Write dates — 2026 crises cluster in the last 30 days so the 30-day
# frontend filter shows them as "current"; older years spread across the year.
TODAY = datetime.date(2026, 5, 18)

def rand_date(year):
    if year == 2026:
        start = TODAY - datetime.timedelta(days=29)
        end   = TODAY
    else:
        start = datetime.date(year, 1, 1)
        end   = datetime.date(year, 12, 31)
    delta = (end - start).days
    d = start + datetime.timedelta(days=random.randint(0, delta))
    return d.isoformat() + 'T12:00:00'

updates = [(rand_date(yr), cid) for cid, yr in assignments.items()]
c.executemany("UPDATE crises SET date_start = ? WHERE id = ?", updates)
conn.commit()

# Verify
rows = conn.execute("""
    SELECT strftime('%Y', date_start) yr, COUNT(*) n
    FROM crises GROUP BY yr ORDER BY yr
""").fetchall()
print("Crisis distribution after spread:")
for yr, n in rows:
    print(f"  {yr}: {n} crises")

conn.close()
print("Done.")
