// Types derived from the live backend response at GET http://localhost:5000/api/crises
// (verified by curl against the running Flask dev server on 2026-09-29).

export interface CrisisDomains {
  economic: number;
  environment: number;
  information: number;
  military: number;
  political: number;
  technology: number;
}

export interface Crisis {
  // IMPORTANT: id is a real string (e.g. "gdelt_1324698776"), never coerce to number.
  id: string;
  analysis: string;
  confidence: number;
  country: string;
  date: string;
  date_scheduled: string | null;
  domains: CrisisDomains;
  impact: string;
  is_verified: boolean;
  lat: number;
  location_confidence: number;
  lon: number;
  severity: number;
  source: string;
  source_url: string;
  stakeholders: string[];
  status: string;
  title: string;
  type: string;
  // 'global' | 'local' — added by the backend's scope classification work
  // (Phase 10.4). Optional/undefined until that backend change ships, so
  // callers must treat a missing value as unknown rather than assuming
  // 'global'.
  scope?: 'global' | 'local';
}

// The lean shape returned by GET /api/crises?view=map — everything the globe,
// the Events list and the Analysis header read. The full row (analysis,
// domains, stakeholders...) comes from GET /api/crises/<id> when needed.
export type CrisisSummary = Pick<
  Crisis,
  'id' | 'title' | 'country' | 'type' | 'severity' | 'scope' | 'date' | 'lat' | 'lon' | 'source_url'
>;

// GET /api/crises/<id>/scenarios (premium). Likelihood is a qualitative word on
// purpose — the backend never returns a numeric probability.
export type ScenarioLikelihood = 'less likely' | 'plausible' | 'more likely';

export interface Scenario {
  title: string;
  likelihood: ScenarioLikelihood;
  timeframe: string;
  summary: string;
  what_would_drive_it: string[];
  watch_for: string[];
  who_is_affected: string[];
}

export interface ScenariosResponse {
  scenarios: Scenario[];
  assumptions: string[];
  // The real facts the scenarios were grounded in.
  based_on: { severity: number; trend: string | null; source_text: boolean; relationships: string[] };
  disclaimer: string;
  model: string;
  timestamp: string;
}

// Dashboard (premium). A saved event is a server-side snapshot of the crisis at
// save time, so it still opens after the event is archived from the live list.
export interface SavedEvent {
  crisis_id: string;
  title: string;
  country: string;
  type: string;
  severity: number;
  lat: number;
  lon: number;
  source_url: string | null;
  event_date: string | null;
  saved_at: string;
}

export interface UserPrefs {
  // Outlet hostnames whose events are hidden from the list and globe.
  hidden_outlets: string[];
}

// Event comments (premium to post; anyone can read). Plain text only.
export interface EventComment {
  id: string;
  body: string;
  author_name: string;
  created_at: string;
  mine: boolean;
  // Auto-hidden after enough reports; only its author (and the admin) sees it.
  hidden: boolean;
}

export interface CommentsPage {
  comments: EventComment[];
  next_before: string | null;
}

export interface Profile {
  display_name: string;
}

export type ReportReason = 'spam' | 'abusive' | 'misinformation' | 'other';

// GET /api/me — who the caller is and whether premium UI should unlock.
// The backend enforces premium on its own routes; this only drives the UI.
export interface Me {
  signedIn: boolean;
  userId: string | null;
  plan: 'free' | 'premium';
  premium: boolean;
}

export interface CrisesResponse {
  count: number;
  crises: CrisisSummary[];
}

// Verified live at GET /api/crises/<id> — same shape as a list item plus `news`.
export interface CrisisDetail extends Crisis {
  news: unknown[];
}

// Verified live at GET /api/crises/<id>/briefing.
export interface BriefingSource {
  n: number;
  published: string;
  source: string;
  title: string;
  url: string;
}

// Wikipedia lead image (country profiles) or a Claude-generated illustrative
// image (briefings, when available) — { src, caption }.
export interface WikiImage {
  src: string;
  caption: string;
}

// og:image / og:video extracted from the crisis's own real source_url
// (step 7 of the rewrite plan) — either may be null when the source page
// doesn't have one; never fabricated.
export interface SourceMedia {
  image_url: string | null;
  video_url: string | null;
}

export interface Briefing {
  briefing: string;
  model: string;
  sources: BriefingSource[];
  timestamp: string;
  image?: WikiImage;
  source_media?: SourceMedia;
}

// Verified live at GET /api/countries/<code> (step 4 of the rewrite plan).
export interface CountryDemographics {
  name: string | null;
  official_name: string | null;
  capital: string | null;
  region: string | null;
  subregion: string | null;
  population: number | null;
  area_km2: number | null;
  currencies: { code: string; name: string; symbol: string }[] | null;
  languages: string[] | null;
  borders: string[] | null;
  flag_svg: string | null;
  flag_png: string | null;
}

export interface CountryTopExport {
  hs4: string;
  trade_value_usd: number;
}

export interface CountryTrade {
  top_exports_by_commodity: CountryTopExport[] | null;
  top_exports_source: string | null;
  top_exports_unavailable_reason: string | null;
  gdp_usd_billions: number | null;
  gdp_year: number | null;
  exports_percent_of_gdp: number | null;
  imports_percent_of_gdp: number | null;
  trade_openness_percent_of_gdp: number | null;
}

export interface CountryNarrative {
  // 'static-facts-only' when no ANTHROPIC_API_KEY is configured (this dev
  // environment's actual state) — mirrors Briefing['model']'s convention.
  model: string;
  geography_infrastructure: string | null;
  world_contribution: string | null;
}

export interface CountryProfile {
  country_code: string;
  demographics: CountryDemographics;
  demographics_source: string;
  trade: CountryTrade;
  narrative: CountryNarrative;
  image: WikiImage | null;
  generated_at: string;
}

// Verified live at GET /api/weather/storms — real active weather hazards
// (tropical cyclones, floods, wildfires, droughts) from GDACS.
export type HazardType = 'TC' | 'FL' | 'WF' | 'DR';

export interface Storm {
  id: number;
  name: string | null;
  event_type: string;
  hazard: string | null;
  description: string | null;
  affected_countries: string[];
  severity: number | null;
  severity_unit: string | null;
  lat: number | null;
  lon: number | null;
  alert_level: string | null;
  severity_kmh: number | null;
  severity_text: string | null;
  country: string | null;
  from_date: string | null;
  to_date: string | null;
  date_modified: string | null;
  report_url: string | null;
  source: string;
}

export interface StormsResponse {
  storms: Storm[];
  count: number;
  source: string;
  generated_at: string;
}

// GET /api/weather/forecast — current conditions, next 48 hours and 7 days.
// Units come from the API (metric); the UI converts for display.
export interface ForecastCurrent {
  time: string | null;
  temperature_2m: number | null;
  apparent_temperature: number | null;
  relative_humidity_2m: number | null;
  precipitation: number | null;
  weather_code: number | null;
  wind_speed_10m: number | null;
  wind_gusts_10m: number | null;
  wind_direction_10m: number | null;
  pressure_msl: number | null;
  cloud_cover: number | null;
  visibility: number | null;
}

export interface Forecast {
  lat: number;
  lon: number;
  timezone: string | null;
  elevation_m: number | null;
  current: ForecastCurrent;
  hourly: {
    time: string[];
    temperature_2m?: number[];
    precipitation_probability?: (number | null)[];
    precipitation?: number[];
    wind_speed_10m?: number[];
    wind_gusts_10m?: number[];
    weather_code?: number[];
  };
  daily: {
    time: string[];
    weather_code?: number[];
    temperature_2m_max?: number[];
    temperature_2m_min?: number[];
    precipitation_sum?: number[];
    precipitation_probability_max?: (number | null)[];
    wind_gusts_10m_max?: number[];
  };
  source: string;
  generated_at: string;
}

// Watchlist places and hazard alerts (premium). `nearby` is computed by the
// server from the live GDACS hazards within the place's radius.
export interface NearbyHazard {
  id: number | null;
  event_type: string | null;
  hazard: string | null;
  name: string | null;
  alert_level: string | null;
  distance_km: number;
}

export interface WatchPlace {
  id: string;
  name: string;
  lat: number;
  lon: number;
  radius_km: number;
  created_at: string;
  nearby: NearbyHazard[];
}

export interface WatchResponse {
  places: WatchPlace[];
  limit: number;
  hazards_available: boolean;
}

export interface NewWatchPlace {
  name: string;
  lat: number;
  lon: number;
  radius_km: number;
}

export interface AlertItem {
  id: string;
  place_id: string;
  place_name: string | null;
  hazard_key: string;
  hazard_type: string;
  title: string;
  alert_level: string;
  distance_km: number;
  created_at: string;
  read_at: string | null;
}

export interface AlertsResponse {
  alerts: AlertItem[];
  unread: number;
}

export type AlertMinLevel = 'green' | 'orange' | 'red';

export interface AlertSettings {
  alert_email: boolean;
  alert_min_level: AlertMinLevel;
}

export interface GeoResult {
  name: string;
  country: string | null;
  admin1: string | null;
  lat: number;
  lon: number;
}
