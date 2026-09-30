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

export interface CrisesResponse {
  count: number;
  crises: Crisis[];
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

// Verified live at GET /api/weather/storms (step 5 of the rewrite plan) —
// real active tropical cyclones from GDACS.
export interface Storm {
  id: number;
  name: string | null;
  event_type: string;
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
