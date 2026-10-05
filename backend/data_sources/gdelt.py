import re
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from ._shared import logger
from .newsapi import NewsBasedCrisisDetector
from .utils import fetch_real_page_metadata

# GDELT's Event Database — real, free, no key/registration required
# (confirmed live: https://www.gdeltproject.org/data.html states "100% free
# and open"). Added as an ACLED alternative after ACLED's own myACLED access
# system turned out to gate real API reads behind a Research-tier/licensed
# account — see GDELTConnector below. lastupdate.txt always points at the
# 3 real files (export/mentions/gkg) for the most recent 15-minute window;
# GDELT_EVENT_URL_TEMPLATE reconstructs the export file URL for any other
# real, valid 15-minute-aligned timestamp GDELT has published.
GDELT_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_EVENT_URL_TEMPLATE = "http://data.gdeltproject.org/gdeltv2/{ts}.export.CSV.zip"

# CAMEO event root codes (2-digit prefix of EventCode) mapped to this app's
# crisis types, mirroring ACLED_TYPE_MAP's pattern above. Only the codes
# that can actually appear under GDELTConnector's QuadClass 3/4 filter
# (verbal + material conflict) are listed — codes 01-09 (cooperation) never
# reach this map since those rows are filtered out before type lookup.
# Roots whose events are things people SAY or announce (demand, disapprove, reject,
# threaten, reduce relations), and CAMEO 172 (administrative sanctions, the one
# non-physical part of root 17 "coerce"). They have no physical site, yet GDELT
# still gives them a point, usually where the actors or the dateline are, so the
# map draws them differently. Every other root we keep (protest, force posture,
# arrests and seizures, assault, fight, mass violence) happened somewhere.
GDELT_STATEMENT_ROOTS = frozenset({'10', '11', '12', '13', '16'})
GDELT_STATEMENT_CODE_PREFIXES = ('172',)
GDELT_PHYSICAL_ROOTS = frozenset({'14', '15', '17', '18', '19', '20'})


def cameo_kind(code):
    """'statement' | 'physical' for a CAMEO event code ("112", "1823"), or None
    when the code is missing, malformed or outside the conflict roots we keep."""
    text = str(code or '').strip()
    if len(text) < 2 or not text[:2].isdigit():
        return None
    if text[:2] in GDELT_STATEMENT_ROOTS or text.startswith(GDELT_STATEMENT_CODE_PREFIXES):
        return 'statement'
    if text[:2] in GDELT_PHYSICAL_ROOTS:
        return 'physical'
    return None


GDELT_TYPE_MAP = {
    '10': 'diplomatic',    # DEMAND
    '11': 'diplomatic',    # DISAPPROVE
    '12': 'diplomatic',    # REJECT
    '13': 'diplomatic',    # THREATEN
    '14': 'civil_unrest',  # PROTEST
    '15': 'military',      # EXHIBIT FORCE POSTURE
    '16': 'diplomatic',    # REDUCE RELATIONS
    '17': 'diplomatic',    # COERCE
    '18': 'conflict',      # ASSAULT
    '19': 'conflict',      # FIGHT
    '20': 'conflict',      # USE UNCONVENTIONAL MASS VIOLENCE
}

# Real CAMEO root-verb phrasing (the standard, published CAMEO taxonomy —
# not invented), used to build a more specific auto-title than the old
# "{actor1} — {crisis_type} event in {country}" pattern — e.g. "Russia
# fights Ukraine" instead of "UNITED STATES — conflict event in Israel".
# {a2} is filled with either the real Actor2Name or, when GDELT didn't
# resolve one (common for PROTEST-type events with no clear counterparty),
# the country name — see GDELTConnector._build_title.
GDELT_EVENT_VERB = {
    '10': 'demands action from {a2}',
    '11': 'criticizes {a2}',
    '12': 'rejects {a2}',
    '13': 'threatens {a2}',
    '14': 'protests against {a2}',
    '15': 'shows military force near {a2}',
    '16': 'reduces relations with {a2}',
    '17': 'pressures {a2}',
    '18': 'attacks {a2}',
    '19': 'fights {a2}',
    '20': 'uses mass violence against {a2}',
}


# URL substrings that reliably signal content outside this tool's purpose
# (real-world geopolitical crises) — GDELT's automated CAMEO extraction
# regularly misclassifies entertainment/sports/celebrity writing as
# conflict, since that kind of prose is full of words like "attack",
# "battle", and "clash" used non-literally (a concert review's "blistering
# assault of guitar riffs", a sports recap's "battle for the title").
# Confirmed directly against this app's live data before picking this list
# — e.g. a Deep Purple album/tour announcement (URL had no "/music/" path
# segment, just these slug words) generated 74 separate fabricated
# "country X fights country Y" crisis records, one for seemingly every
# pair of countries on the tour's stop list; a celebrity gossip URL
# generated 16 more. Path segments are the safe, unambiguous signal (a
# real armed-conflict story is never filed under an outlet's /celebrity/
# or /entertainment/ section); the handful of added slug words come
# directly from the Deep Purple case and are similarly safe — none of them
# plausibly appear in a real conflict/crisis headline.
GDELT_OFFTOPIC_URL_SIGNALS = (
    '/entertainment/', '/celebrity/', '/tvshowbiz/', '/showbiz/', '/gossip/',
    '/music/', '/movies/', '/film/', '/gaming/', '/sports/', '/sport/',
    '/lifestyle/', '/arts-and-entertainment/',
    'album', 'box-set', 'world-tour', 'setlist',
    # Added from real, confirmed-live false positives (not guessed): a
    # wrestlezone.com pro-wrestling story and a hindustantimes.com
    # /astrology/horoscope/ page both cleared every existing gate and
    # became live Crisis rows — 'wrestl' and 'astrology'/'horoscope'
    # weren't covered by any signal above.
    'astrology', 'horoscope', 'wrestl',
)

# Local crime-blotter stories ("woman charged in bus crash," "seven
# arrested on drug charges") aren't geopolitical crises either, but —
# unlike the signals above — this one's genuinely ambiguous: the same
# "/crime/" path or "arrested"/"indicted" wording could just as easily be
# a real war-crimes or state-violence story this tool should keep. Per
# explicit instruction: log a real, visible flag when one of these matches
# (searchable in the sync logs) rather than silently rejecting the row —
# a deliberately softer, reversible signal, not a filter.
GDELT_POSSIBLY_OFFTOPIC_SIGNALS = (
    '/crime/', 'arrested', 'indicted', 'mugshot', 'sentenced-to',
    'charged-with-murder', 'charged-with-manslaughter',
)

# GDELT often explodes ONE article into several rows (one per pairing of the places it
# mentions) and lets many outlets repeat one wire story, so a third of the rows were repeats.
# Those rows used to be capped and dropped here, which also threw away their sources. They are
# now kept and merged into one story afterwards (services/stories.py), so the story names every
# outlet that reported it.

# GDELT's QuadClass/CAMEO-code gate has no text-relevance check at all (unlike
# NewsBasedCrisisDetector.CRISIS_KEYWORDS for the NewsAPI path) — a CAMEO
# classifier mis-tags ordinary commercial disputes as conflict language just
# as readily as real ones (confirmed live: a Qualcomm/Apple patent-licensing
# story was CAMEO-coded as coercion between "COMPANIES" and "CHINA"). Fixed
# by using real, already-fetched-for-nothing data GDELT provides in every
# row: Actor1Type1Code/Actor2Type1Code (CAMEO/PLOVER actor-role codes).
# Verified directly against a live GDELT sample (335 real QuadClass 3/4
# rows) rather than assumed: a real state actor referenced by its own
# name/country code (e.g. "CANADA", "TURKEY") has NO type code populated at
# all — type codes are for role categories layered on top of or instead of
# a bare state actor — so a positive allow-list of GOV/MIL/etc. would have
# rejected the majority of genuinely real state-vs-state rows (400 of 670
# actor-type slots in the sample were blank). The one type code that
# reliably marks a NON-geopolitical actor regardless of what's on the other
# side is BUS/MNC (a business/corporate entity) — confirmed responsible for
# ~9% of the sample (29/335 rows) including every business-dispute example
# found, with zero observed false positives against real government/police/
# military/rebel-coded rows.
GDELT_NONSTATE_ACTOR_TYPES = {'BUS', 'MNC'}

# A second, independent actor-quality signal: generic role-nouns used as
# the actor *name* itself (not caught by GDELT_NONSTATE_ACTOR_TYPES above,
# since the actor *type* field is blank for these rows — only the name
# string is generic). Verified against a live 254-row QuadClass-3/4 sample:
# every one of 8 rows naming "Company"/"Companies"/"Business" as an actor
# was real noise (a home-security product review, a seafood plant closure,
# a community business gala, a utility regulatory filing) — zero real
# geopolitical false positives.
#
# Extended in Phase 22's follow-up investigation after live sampling ~20
# candidate generic-noun "actors" (11 real examples each, via each row's
# actual source_url): 'attorney'/'prison'/'judge'/'criminal' were the only
# four with ZERO real geopolitical hits across all samples — exclusively
# routine local crime/legal-process coverage (misdemeanor prosecutions,
# court sentencings, custody disputes, fraud arraignments; several
# "criminal" rows weren't even news articles, just court-document-database
# or tag-aggregator pages). Every other candidate sampled (police,
# government, school, authorities, residents, media, community, congress,
# administration, military, governor, voter, student, gang, worker,
# university) turned up at least one confirmed real, sometimes significant
# geopolitical story in the same sampling (an Ebola outbreak in Congo, a
# Trump-Xi meeting, Israel-Qatar tension, Taiwan-Tuvalu diplomacy, Haiti
# gang violence/OAS deployment, India worker abductions, a Colombia
# health-worker-violence story) — those are deliberately left untouched,
# the same "don't over-reach past what's actually confirmed noisy" lesson
# already learned from the reverted 'AGR' actor-TYPE exclusion (a 2-of-3
# false-positive rate against real news) and from keeping
# "police"/"military"/"authorities"/"residents" out of this set originally.
GDELT_GENERIC_ACTOR_NAMES = {
    'company', 'companies', 'business', 'corporation',
    'attorney', 'prison', 'judge', 'criminal',
}

# The self-referential check above (actor1_name_raw == actor2_name_raw)
# only catches an EXACT string match — it misses a self-referential pair
# where GDELT extracted the demonym/adjectival form for one side and the
# plain country name for the other (e.g. "Philippine criticizes
# Philippines", "Japanese fights Japan" at severity 100). Confirmed live
# via a full-DB scan: real, repeated pairs including 'Africa'/'South
# Africa' (n=35 — not a demonym but a confirmed GDELT truncation quirk;
# Actor2Name in every one of these rows is literally "South Africa", so
# it's genuinely self-referential, just via truncation rather than an
# adjectival form). Deliberately a small, curated, exact-match map, NOT a
# general substring-containment rule — a substring rule would have real
# false-positive risk this session already learned to avoid (e.g. "Korea"
# legitimately appears inside both "North Korea" and "South Korea"
# without those being self-referential; "Russia" vs "Ukraine" are two
# real, distinct countries in real conflict, not a demonym pair, even
# though a naive substring/fuzzy check flagged them during this
# investigation). Values are lowercase to match _normalize_actor_for_
# selfref's own lowercasing.
GDELT_DEMONYM_TO_COUNTRY = {
    'philippine': 'philippines',
    'australian': 'australia',
    'south korean': 'south korea',
    'north korean': 'north korea',
    'saudi': 'saudi arabia',
    'german': 'germany',
    'nigerian': 'nigeria',
    'thai': 'thailand',
    'azerbaijani': 'azerbaijan',
    'sri lankan': 'sri lanka',
    'japanese': 'japan',
    'algerian': 'algeria',
    'namibian': 'namibia',
    'malian': 'mali',
    'taiwanese': 'taiwan',
    'costa rican': 'costa rica',
    'kenyan': 'kenya',
    'nicaraguan': 'nicaragua',
    'africa': 'south africa',
}

# A THIRD, independent noise signal, distinct from the two above: a row
# where GDELT resolved NO Actor1Name at all (not a generic name — no name),
# combined with a violence-coded CAMEO root. Confirmed live: of 1,110 rows
# carrying the generic fallback title (see GDELT_GENERIC_FALLBACK_TITLE_
# PREFIX below, which fires exactly when Actor1Name is blank), the ones
# under root 19 (FIGHT) averaged severity 99.7 (366 rows) and root 18
# (ASSAULT) averaged 92.6 (31 rows) — the single largest contributor to
# the severity-90-100 band. A live 15-row sample of root-19 blank-actor
# rows found 13 confirmed non-geopolitical (a school lockdown, a bus
# crash, a commercial building fire, infant deaths, a law-enforcement
# anniversary piece) — a real armed-conflict/mass-violence event
# significant enough to be geopolitical almost always has an identifiable
# state or organized-group actor; "fight"/"assault"-coded text with NO
# actor GDELT could name at all is a strong (confirmed ~87% in-sample)
# signal of local crime/accident content GDELT's vocabulary-based CAMEO
# classifier miscoded, not a real gap in the two filters above (which only
# ever look at NAMED actors). Roots 10-17 (diplomatic/verbal, much lower
# severity) are deliberately excluded — not the severity complaint's
# driver, and this exact combination wasn't verified for those roots.
GDELT_BLANK_ACTOR_VIOLENT_ROOTS = {'18', '19', '20'}

# The exact title _build_title produces when Actor1Name is blank — used
# both to gate GDELT_BLANK_ACTOR_VIOLENT_ROOTS's retroactive counterpart
# and to exclude these rows from the syndication fan-out cap below (they
# share this one uninformative title across genuinely distinct real
# events/locations — confirmed live: 888 distinct source_urls behind it —
# so capping by shared title would wrongly delete real, different events).
GDELT_GENERIC_FALLBACK_TITLE_PREFIX = "Conflict-related event in "


class GDELTConnector:
    """
    Free, real alternative/addition to ACLED — the GDELT Project's Event
    Database (https://www.gdeltproject.org/data.html, confirmed live as
    "100% free and open", no registration or key). Monitors global news
    every 15 minutes and publishes structured, CAMEO-coded events with real
    lat/lon, the same shape of data ACLED provides.

    File format: tab-separated, no header, 61 fixed columns per row. Column
    positions below were verified by downloading and inspecting a real live
    file during development, not just the public docs, since off-by-one
    errors in this schema are a known pitfall.
    """
    _COL_EVENT_CODE = 26
    _COL_QUAD_CLASS = 29
    _COL_GOLDSTEIN = 30
    _COL_NUM_SOURCES = 32
    _COL_NUM_ARTICLES = 33
    _COL_ACTOR1_NAME = 6
    _COL_ACTOR1_TYPE1 = 12
    _COL_ACTOR2_NAME = 16
    _COL_ACTOR2_TYPE1 = 22
    _COL_ACTION_GEO_FULLNAME = 52
    _COL_ACTION_GEO_LAT = 56
    _COL_ACTION_GEO_LONG = 57
    _COL_DATE_ADDED = 59
    _COL_SOURCE_URL = 60
    _MIN_COLUMNS = 61

    @staticmethod
    def _get_recent_timestamps():
        """The real, currently-published GDELT event-file timestamp (from
        lastupdate.txt) plus the 3 that precede it at 15-minute intervals —
        covers a full hour so nothing is missed between this app's hourly
        sync runs. No persisted sync-cursor needed: `_upsert_crisis()`
        already dedups by id, so a little overlap between runs is harmless,
        the same way ACLED/NewsAPI's own rolling-window fetches work."""
        response = requests.get(GDELT_LASTUPDATE_URL, timeout=10)
        response.raise_for_status()

        latest_ts = None
        for line in response.text.splitlines():
            if '.export.CSV.zip' in line:
                url = line.strip().split()[-1]
                latest_ts = url.rsplit('/', 1)[-1].split('.export.CSV.zip')[0]
                break
        if not latest_ts:
            raise ValueError("lastupdate.txt did not contain an export.CSV.zip entry")

        latest_dt = datetime.strptime(latest_ts, '%Y%m%d%H%M%S')
        return [(latest_dt - timedelta(minutes=15 * i)).strftime('%Y%m%d%H%M%S') for i in range(4)]

    @staticmethod
    def _fetch_event_rows(timestamp):
        """Download and unzip one real GDELT event file, returning its raw
        tab-separated rows. Returns [] on any failure (network, missing
        file — GDELT occasionally publishes late) rather than raising, so
        one bad window never breaks the other 3."""
        import zipfile
        import io

        url = GDELT_EVENT_URL_TEMPLATE.format(ts=timestamp)
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                name = zf.namelist()[0]
                text = zf.read(name).decode('utf-8', errors='replace')
            return [line.split('\t') for line in text.splitlines() if line.strip()]
        except Exception as e:
            logger.warning(f"GDELT fetch failed for {timestamp}: {e}")
            return []

    @staticmethod
    def _build_title(actor1_name, actor2_name, event_root, country):
        """A more specific auto-title than a generic '{type} event in
        {country}' — built from real fields already in the row: both
        actors (when GDELT resolved them) and the real CAMEO root-verb
        phrasing (GDELT_EVENT_VERB). Still not a real headline (GDELT's
        raw export has no article text/title at all, for copyright
        reasons) — see GDELTConnector.fetch_real_headline for that."""
        actor1 = actor1_name.strip().title() if actor1_name.strip() else None
        actor2 = actor2_name.strip().title() if actor2_name.strip() else None
        verb_template = GDELT_EVENT_VERB.get(event_root)

        if actor1 and verb_template:
            return f"{actor1} {verb_template.format(a2=actor2 or country)}"
        if actor1:
            return f"{actor1} — conflict-related event in {country}"
        return f"Conflict-related event in {country}"

    @staticmethod
    def _country_from_geo_fullname(full_name):
        """GDELT's ActionGeo_CountryCode is FIPS 10-4, not ISO — this app's
        Crisis.country convention is a real country NAME string (matching
        Actor.name, per LOCATION_MAP/ACLED's own convention). ActionGeo_
        FullName is a real, already-geocoded hierarchical description
        ("City, Admin1, Country" or just "Country" for a country-level
        geo-type) — the country name is reliably its last comma segment,
        confirmed against real sample rows during development, so this
        parses it directly rather than maintaining a ~200-entry FIPS
        lookup table."""
        country, _segments = GDELTConnector._parse_geo_fullname(full_name)
        return country

    @staticmethod
    def _parse_geo_fullname(full_name):
        """Like _country_from_geo_fullname, but also returns the real
        segment count — GDELT's own ActionGeo_Type precision is encoded in
        how many comma segments ActionGeo_FullName has (1 = country-level
        only, e.g. "Iran"; 2 = admin1/state-level, e.g. "Texas, United
        States"; 3 = real city-level, e.g. "Kyiv, Kyiv, Ukraine") — used to
        derive a real, honest location_confidence instead of the flat
        constant every GDELT crisis used to get regardless of whether
        GDELT actually resolved a precise incident site or just defaulted
        to a country/capital point (a real, code-documented GDELT
        limitation — see get_crisis_real_headline's docstring in app.py)."""
        if not full_name:
            return None, 0
        parts = [p.strip() for p in full_name.split(',') if p.strip()]
        return (parts[-1] if parts else None), len(parts)

    @staticmethod
    def _parse_row(fields):
        """One raw TSV row -> a crisis dict, or None if it's not a real
        conflict-relevant row (wrong QuadClass, unmapped event type, or
        missing the geo/severity data a real crisis record needs)."""
        if len(fields) < GDELTConnector._MIN_COLUMNS:
            return None

        # Off-topic check first — cheapest possible reject, and no point
        # computing type/geo/severity for a row that's getting discarded
        # anyway (see GDELT_OFFTOPIC_URL_SIGNALS for why this exists).
        source_url_lower = (fields[GDELTConnector._COL_SOURCE_URL] or '').lower()
        if any(signal in source_url_lower for signal in GDELT_OFFTOPIC_URL_SIGNALS):
            return None

        # Ambiguous case — flagged, not filtered (see
        # GDELT_POSSIBLY_OFFTOPIC_SIGNALS docstring). The row still gets
        # parsed and shown normally; this only leaves a real, greppable
        # trail in case someone wants to review how much local-crime noise
        # is coming through.
        if any(signal in source_url_lower for signal in GDELT_POSSIBLY_OFFTOPIC_SIGNALS):
            logger.info(f"GDELT possibly-offtopic (not filtered): {fields[GDELTConnector._COL_SOURCE_URL]}")

        quad_class = fields[GDELTConnector._COL_QUAD_CLASS]
        if quad_class not in ('3', '4'):  # keep only verbal + material conflict
            return None

        # Reject when either actor is a business/corporate entity — see
        # GDELT_NONSTATE_ACTOR_TYPES for why this (not a GOV/MIL allow-list)
        # is the real, data-verified signal for "not actually geopolitical".
        actor1_type = fields[GDELTConnector._COL_ACTOR1_TYPE1].strip()
        actor2_type = fields[GDELTConnector._COL_ACTOR2_TYPE1].strip()
        if actor1_type in GDELT_NONSTATE_ACTOR_TYPES or actor2_type in GDELT_NONSTATE_ACTOR_TYPES:
            return None

        actor1_name_raw = fields[GDELTConnector._COL_ACTOR1_NAME].strip()
        actor2_name_raw = fields[GDELTConnector._COL_ACTOR2_NAME].strip()

        # These three signals (generic-actor-name, self-referential/demonym
        # actor pair, blank-actor-under-violent-root) were built and
        # live-verified across multiple phases as reliable indicators of
        # routine local crime/accident/human-interest content GDELT's CAMEO
        # parser mis-tags as conflict — real content, just not geopolitical.
        # Per the Local/Global scope feature, these no longer discard the
        # row: they classify it as scope='local' and parsing continues
        # normally (country/severity/title/etc. still get computed). Only
        # a row that never trips any of these becomes scope='global'.
        scope = 'global'

        # Same generic-corporate signal as GDELT_NONSTATE_ACTOR_TYPES above,
        # applied to the actor NAME string — see GDELT_GENERIC_ACTOR_NAMES
        # for why type-only wasn't enough.
        if actor1_name_raw.lower() in GDELT_GENERIC_ACTOR_NAMES or actor2_name_raw.lower() in GDELT_GENERIC_ACTOR_NAMES:
            scope = 'local'

        # A self-referential pair ("United States criticizes United
        # States") is never a real geopolitical relationship between two
        # parties — confirmed live (7/7 real examples: a drug-policy
        # statement, a grand-jury indictment, talk-radio commentary, a
        # theft-conspiracy sentencing, a university case, GOP-primary
        # commentary — all purely domestic noise where GDELT's actor
        # resolver defaulted to the same entity on both sides).
        if actor1_name_raw and GDELTConnector._normalize_actor_for_selfref(actor1_name_raw) == \
                GDELTConnector._normalize_actor_for_selfref(actor2_name_raw):
            scope = 'local'

        event_root = fields[GDELTConnector._COL_EVENT_CODE][:2]
        crisis_type = GDELT_TYPE_MAP.get(event_root)
        if crisis_type is None:
            return None

        # See GDELT_BLANK_ACTOR_VIOLENT_ROOTS for the live-data
        # verification behind this: a blank Actor1Name combined
        # specifically with a violence-coded root is confirmed dominated
        # by non-geopolitical noise (local crime/accident stories using
        # violent vocabulary), unlike the same blank-actor case under a
        # diplomatic/verbal root, which is left untouched.
        if not actor1_name_raw and event_root in GDELT_BLANK_ACTOR_VIOLENT_ROOTS:
            scope = 'local'

        try:
            lat = float(fields[GDELTConnector._COL_ACTION_GEO_LAT])
            lon = float(fields[GDELTConnector._COL_ACTION_GEO_LONG])
        except (ValueError, IndexError):
            return None
        if lat == 0 and lon == 0:  # GDELT's placeholder for "no real geo resolved"
            return None

        country, geo_segments = GDELTConnector._parse_geo_fullname(
            fields[GDELTConnector._COL_ACTION_GEO_FULLNAME]
        )
        if not country:
            return None
        # Real precision signal, not a flat guess — see _parse_geo_fullname.
        # 1 segment (country-only) is GDELT's fallback for events with no
        # resolvable physical site (a "threat" or "demand" has no address);
        # 3 segments is a genuine city-level resolution.
        location_confidence = {1: 55, 2: 70}.get(geo_segments, 85)

        # Severity — real, not fabricated: GoldsteinScale is GDELT's own
        # published -10 (maximally conflictual) .. +10 (maximally
        # cooperative) intensity score for this exact event. A maximally
        # conflictual event scores 100; anything trending cooperative
        # (rare but possible even inside QuadClass 3/4's edge cases)
        # clamps to a low, not negative, severity.
        try:
            goldstein = float(fields[GDELTConnector._COL_GOLDSTEIN])
        except (ValueError, IndexError):
            goldstein = 0.0
        severity = max(0, min(100, round(-goldstein * 10)))

        # Confidence — real, not a flat constant: more independent sources
        # corroborating the same event is a real (if rough) signal.
        try:
            num_sources = int(float(fields[GDELTConnector._COL_NUM_SOURCES]))
        except (ValueError, IndexError):
            num_sources = 1
        confidence = max(50, min(95, 50 + num_sources * 5))

        global_event_id = fields[0]
        date_added_raw = fields[GDELTConnector._COL_DATE_ADDED]
        try:
            date_start = datetime.strptime(date_added_raw, '%Y%m%d%H%M%S')
        except ValueError:
            date_start = datetime.utcnow()

        actor_text = actor1_name_raw + ' ' + actor2_name_raw
        stakeholders = NewsBasedCrisisDetector._find_stakeholders(actor_text)

        source_url = fields[GDELTConnector._COL_SOURCE_URL]
        title = GDELTConnector._build_title(
            actor1_name_raw,
            actor2_name_raw,
            event_root,
            country,
        )

        return {
            'id': f"gdelt_{global_event_id}",
            'type': crisis_type,
            'title': title,
            'country': country,
            'latitude': lat,
            'longitude': lon,
            'severity': severity,
            'confidence': confidence,
            'location_confidence': location_confidence,
            'event_kind': cameo_kind(fields[GDELTConnector._COL_EVENT_CODE]),
            'date_start': date_start,
            'analysis': f"GDELT-monitored event (CAMEO {fields[GDELTConnector._COL_EVENT_CODE]}), reported via {source_url}",
            'impact': f"{num_sources} source(s) reporting",
            'source': 'GDELT',
            'source_id': global_event_id,
            'source_url': source_url,
            'is_verified': False,
            'stakeholders': ','.join(stakeholders),
            'scope': scope,
        }

    _CAMEO_CODE_RE = re.compile(r'CAMEO (\d+)')

    @staticmethod
    def _extract_event_root_from_analysis(analysis_text):
        """Retroactive recovery of the 2-digit CAMEO event-root code from
        the `analysis` string _parse_row stores on every crisis it builds
        (f"GDELT-monitored event (CAMEO {code}), ..."), for cleaning up
        existing rows that predate a filter needing the root — the raw
        TSV fields aren't kept once a row becomes a stored Crisis."""
        if not analysis_text:
            return None
        m = GDELTConnector._CAMEO_CODE_RE.search(analysis_text)
        if not m:
            return None
        return m.group(1)[:2]

    @staticmethod
    def _is_blank_actor_violent_root(title, analysis_text):
        """Retroactive counterpart to the GDELT_BLANK_ACTOR_VIOLENT_ROOTS
        ingestion check above, for rows that predate it."""
        if not (title or '').startswith(GDELT_GENERIC_FALLBACK_TITLE_PREFIX):
            return False
        event_root = GDELTConnector._extract_event_root_from_analysis(analysis_text)
        return event_root in GDELT_BLANK_ACTOR_VIOLENT_ROOTS

    @staticmethod
    def _normalize_actor_for_selfref(name):
        """Normalizes a demonym/adjectival actor form (or GDELT's own
        'Africa'-for-'South Africa' truncation quirk) to the plain country
        name it refers to, so a self-referential check catches a pair like
        "Philippine"/"Philippines" that an exact string match misses — see
        GDELT_DEMONYM_TO_COUNTRY for the live-verified curated list this
        draws from (deliberately not a general substring/fuzzy rule)."""
        if not name:
            return ''
        key = name.strip().lower()
        return GDELT_DEMONYM_TO_COUNTRY.get(key, key)

    @staticmethod
    def _is_self_referential_title(title):
        """Retroactive detection for existing rows that predate the
        Actor1Name==Actor2Name ingestion check. Reconstructs the check
        from the auto-generated title's shape for a self-referential pair
        ("{X} {verb phrase} {X}") since the raw actor fields aren't kept
        once a row becomes a stored Crisis — _build_title always puts
        actor1 first and actor2 (or the country, when actor2 is blank) at
        the very end of one of GDELT_EVENT_VERB's fixed verb phrases.
        Both sides are run through _normalize_actor_for_selfref so a
        demonym-form pair ("Japanese fights Japan") is caught the same
        way an exact-match pair is.

        Also covers a legacy single-actor title format ("{actor} —
        conflict event in {country}") no longer produced by the current
        _build_title (which emits "— conflict-related event in {country}"
        instead, confirmed live to be unreachable dead code today since
        GDELT_EVENT_VERB covers every GDELT_TYPE_MAP root) but still
        present on older rows — self-referential there means the single
        actor IS the country (confirmed live: "UNITED STATES — conflict
        event in United States", "CHINA — conflict event in China")."""
        if not title:
            return False
        if ' — conflict event in ' in title:
            actor, country = title.split(' — conflict event in ', 1)
            if GDELTConnector._normalize_actor_for_selfref(actor) == \
                    GDELTConnector._normalize_actor_for_selfref(country):
                return True
        for verb_template in GDELT_EVENT_VERB.values():
            prefix = verb_template.split('{a2}')[0]
            marker = f' {prefix}'
            idx = title.find(marker)
            if idx == -1:
                continue
            actor1 = title[:idx].strip()
            actor2 = title[idx + len(marker):].strip()
            if actor1 and GDELTConnector._normalize_actor_for_selfref(actor1) == \
                    GDELTConnector._normalize_actor_for_selfref(actor2):
                return True
        return False

    @staticmethod
    def _starts_with_generic_actor_name(title):
        """Retroactive counterpart to the GDELT_GENERIC_ACTOR_NAMES
        ingestion check, applied to the leading actor segment of an
        existing title (_build_title always puts actor1 first)."""
        if not title:
            return False
        leading = title.split(' ', 1)[0].strip().lower().rstrip('.,')
        return leading in GDELT_GENERIC_ACTOR_NAMES

    # Bounded — this runs once per sync against whatever survives the three
    # fan-out caps (real-world observed: ~500 rows/sync), not the full raw
    # feed. 8 concurrent workers keeps a real, ~8s-per-request worst case
    # (see fetch_real_page_metadata's own timeout) from making sync
    # duration scale linearly with row count; tune live if a real sync
    # run's wall-clock time (logged below) turns out too slow or too eager.
    _TITLE_RESOLUTION_WORKERS = 8

    @staticmethod
    def _resolve_real_titles(crises):
        """Replaces each row's auto-generated CAMEO-verb/fallback title with
        the real article headline, fetched from its own real source_url —
        done once here, at sync time, so every downstream reader (API,
        frontend) always sees a real title with no lazy-fetch flash. Never
        fabricates: a row whose fetch fails, times out, or whose page title
        turns out to be unusable (via the same _clean_article_title real
        pages already get cleaned through) keeps its existing honest
        auto-generated title exactly as before — this only ever upgrades a
        title, never leaves one blank or invents one."""
        if not crises:
            return crises

        # One fetch per distinct article, however many rows cite it (one article can be
        # behind several rows, and many rows share a wire story's URL).
        urls = sorted({c['source_url'] for c in crises if c.get('source_url')})
        titles = {}

        def fetch_one(url):
            metadata = fetch_real_page_metadata(url)
            return url, (metadata.get('title') if metadata else None)

        with ThreadPoolExecutor(max_workers=GDELTConnector._TITLE_RESOLUTION_WORKERS) as pool:
            futures = [pool.submit(fetch_one, url) for url in urls]
            for future in as_completed(futures):
                try:
                    url, title = future.result()
                    if title:
                        titles[url] = title
                except Exception as e:
                    logger.warning(f"Real title resolution failed for an article: {e}")

        resolved = 0
        for crisis in crises:
            real_title = titles.get(crisis.get('source_url'))
            if real_title:
                crisis['title'] = real_title
                resolved += 1

        logger.info(f"Resolved real titles for {resolved}/{len(crises)} GDELT crises")
        return crises

    @staticmethod
    def fetch_recent_events():
        """Real, current conflict-relevant events from GDELT — covers the
        last hour (4 real 15-minute files) so nothing is missed between
        this app's hourly sync runs. Returns [] (never raises) on total
        failure, matching ACLED/NewsAPI's own graceful-degradation pattern."""
        try:
            timestamps = GDELTConnector._get_recent_timestamps()
        except Exception as e:
            logger.error(f"GDELT lastupdate.txt fetch failed: {e}")
            return []

        crises = []
        seen_ids = set()
        for ts in timestamps:
            for fields in GDELTConnector._fetch_event_rows(ts):
                crisis = GDELTConnector._parse_row(fields)
                if crisis and crisis['id'] not in seen_ids:
                    seen_ids.add(crisis['id'])
                    crises.append(crisis)

        # Nothing is dropped here: repeats are merged into stories after they are
        # saved (services/stories.py), so their sources are kept. Titles are
        # resolved once per distinct article, so repeats cost no extra fetches.
        start = datetime.utcnow()
        crises = GDELTConnector._resolve_real_titles(crises)
        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(f"Title resolution took {elapsed:.1f}s for {len(crises)} rows")

        logger.info(f"Fetched {len(crises)} conflict-relevant events from GDELT")
        return crises

