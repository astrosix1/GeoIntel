import type * as maplibregl from 'maplibre-gl';

// Forecast and satellite weather layers for Weather mode.
//
//  - Forecast fields (temperature, pressure, rain, wind) come from DWD's global ICON model over its WMS, one raster layer at a time,
//    drawn for a chosen forecast hour. These are FORECASTS, not observations.
//  - Cloud cover and fires come from NASA GIBS and are SATELLITE OBSERVATIONS: cloud cover is the previous day's daily composite,
//    fires are VIIRS detections (a few hours old).
//
// Everything is deliberately thin: the map tiles are fetched by the browser straight from the provider, and every layer carries
// the attribution its licence asks for in the source (the map's attribution control shows it).

export type WeatherField = 'temperature' | 'pressure' | 'rain' | 'wind';

export const WEATHER_FIELDS: { key: WeatherField; label: string; note: string }[] = [
  { key: 'temperature', label: 'Temperature (2 m)', note: 'forecast' },
  { key: 'pressure', label: 'Sea-level pressure', note: 'forecast' },
  { key: 'rain', label: 'Rain, 6 hours to the time shown', note: 'forecast' },
  { key: 'wind', label: 'Wind speed (10 m)', note: 'forecast' },
];

export interface WeatherWant {
  field: WeatherField | null;
  wmsLayer: string | null; // DWD's layer name for the field
  time: string | null; // ISO time with a Z, one of the times the service can draw
  clouds: boolean;
  cloudsDate: string; // YYYY-MM-DD of the daily composite
  fires: boolean;
  firesDate: string; // YYYY-MM-DD of the detections
  darkBase: boolean; // the map underneath is dark (satellite imagery), so black wind barbs are drawn white
}

const WMS = 'https://maps.dwd.de/geoserver/dwd/wms';
const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best';

const FIELD_SOURCE = 'wx-field-src';
const FIELD_LAYER = 'wx-field-layer';
const CLOUD_SOURCE = 'wx-clouds-src';
const CLOUD_LAYER = 'wx-clouds-layer';
const FIRE_SOURCE = 'wx-fires-src';
const FIRE_LAYER = 'wx-fires-layer';
const FIRE_LAYER_NAME = 'VIIRS_SNPP_Thermal_Anomalies_375m_All';

const FIELD_OPACITY: Record<WeatherField, number> = { temperature: 0.6, pressure: 0.85, rain: 0.7, wind: 0.9 };

const DWD_ATTRIBUTION =
  'Forecast: <a href="https://www.dwd.de/" target="_blank" rel="noopener noreferrer">Quelle: Deutscher Wetterdienst</a> (ICON, ' +
  '<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>)';
const NASA_ATTRIBUTION =
  'Satellite: <a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener noreferrer">NASA GIBS</a>';

// A WMS GetMap URL in the shape MapLibre fills in for each tile ({bbox-epsg-3857}). The time is the forecast hour.
export function fieldTileUrl(layer: string, time: string): string {
  return (
    `${WMS}?service=WMS&version=1.3.0&request=GetMap&layers=dwd:${layer}&styles=&format=image/png&transparent=true` +
    `&crs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256&time=${encodeURIComponent(time)}`
  );
}

// The legend picture DWD publishes for a layer (shown beside the map as an ordinary image).
export function fieldLegendUrl(layer: string): string {
  return `${WMS}?service=WMS&version=1.3.0&request=GetLegendGraphic&format=image/png&layer=dwd:${layer}`;
}

export function cloudTileUrl(date: string): string {
  return `${GIBS}/MODIS_Terra_Cloud_Fraction_Day/default/${date}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png`;
}

// Fire detections are published as vector data; GIBS's WMS draws them as transparent dots, so they are used as ordinary raster tiles.
export function fireTileUrl(date: string): string {
  return (
    'https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0' +
    `&LAYERS=${FIRE_LAYER_NAME}&CRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/png&TRANSPARENT=true&TIME=${date}`
  );
}

// Today's date in UTC: the fire layer's detections so far today.
export function todayUtc(now = Date.now()): string {
  return new Date(now).toISOString().slice(0, 10);
}

// The nearest of the available times (ISO strings, sorted) to a moment, or null when there are none.
export function nearestTime(times: string[] | undefined, at: number): string | null {
  if (!times || times.length === 0) return null;
  let best = times[0];
  let bestGap = Math.abs(Date.parse(best) - at);
  for (const t of times) {
    const gap = Math.abs(Date.parse(t) - at);
    if (gap < bestGap) {
      best = t;
      bestGap = gap;
    }
  }
  return best;
}

// Yesterday's date in UTC, the newest daily composite that is complete.
export function yesterdayUtc(now = Date.now()): string {
  return new Date(now - 24 * 3600 * 1000).toISOString().slice(0, 10);
}

// Draws the field and the satellite layers under the radar (when it is on), above the land and below borders and labels.
function anchorId(map: maplibregl.Map): string | undefined {
  const layers = map.getStyle().layers;
  return layers.find((l) => l.id.startsWith('radar-layer-'))?.id ?? layers.find((l) => l.id.startsWith('boundary_'))?.id;
}

function removeIfPresent(map: maplibregl.Map, layer: string, source: string) {
  if (map.getLayer(layer)) map.removeLayer(layer);
  if (map.getSource(source)) map.removeSource(source);
}

// Makes the map match `want`. Idempotent, so it can run on every change; a changed forecast hour only swaps the tile address.
export function syncWeatherLayers(map: maplibregl.Map, want: WeatherWant | null): void {
  const field = want && want.field && want.wmsLayer && want.time ? want : null;

  if (!field) {
    removeIfPresent(map, FIELD_LAYER, FIELD_SOURCE);
  } else {
    const url = fieldTileUrl(field.wmsLayer as string, field.time as string);
    const source = map.getSource(FIELD_SOURCE) as (maplibregl.RasterTileSource & { setTiles?: (t: string[]) => void }) | undefined;
    if (source && typeof source.setTiles === 'function') {
      source.setTiles([url]);
    } else {
      removeIfPresent(map, FIELD_LAYER, FIELD_SOURCE);
    }
    if (!map.getSource(FIELD_SOURCE)) {
      map.addSource(FIELD_SOURCE, { type: 'raster', tiles: [url], tileSize: 256, maxzoom: 6, attribution: DWD_ATTRIBUTION });
    }
    if (!map.getLayer(FIELD_LAYER)) {
      map.addLayer({ id: FIELD_LAYER, type: 'raster', source: FIELD_SOURCE, paint: { 'raster-opacity': 0.6, 'raster-fade-duration': 0 } }, anchorId(map));
    }
    map.setPaintProperty(FIELD_LAYER, 'raster-opacity', FIELD_OPACITY[field.field as WeatherField]);
    // DWD draws wind as black barbs: fine on the light map, lost on satellite imagery, where lifting the black point turns them white.
    map.setPaintProperty(FIELD_LAYER, 'raster-brightness-min', field.field === 'wind' && want?.darkBase ? 1 : 0);
  }

  if (!want || !want.clouds) {
    removeIfPresent(map, CLOUD_LAYER, CLOUD_SOURCE);
  } else {
    const url = cloudTileUrl(want.cloudsDate);
    const source = map.getSource(CLOUD_SOURCE) as (maplibregl.RasterTileSource & { setTiles?: (t: string[]) => void }) | undefined;
    if (source && typeof source.setTiles === 'function') source.setTiles([url]);
    else removeIfPresent(map, CLOUD_LAYER, CLOUD_SOURCE);
    if (!map.getSource(CLOUD_SOURCE)) {
      map.addSource(CLOUD_SOURCE, { type: 'raster', tiles: [url], tileSize: 256, maxzoom: 6, attribution: NASA_ATTRIBUTION });
    }
    if (!map.getLayer(CLOUD_LAYER)) {
      map.addLayer({ id: CLOUD_LAYER, type: 'raster', source: CLOUD_SOURCE, paint: { 'raster-opacity': 0.55, 'raster-fade-duration': 0 } }, anchorId(map));
    }
  }

  if (!want || !want.fires) {
    removeIfPresent(map, FIRE_LAYER, FIRE_SOURCE);
  } else {
    const url = fireTileUrl(want.firesDate);
    const source = map.getSource(FIRE_SOURCE) as (maplibregl.RasterTileSource & { setTiles?: (t: string[]) => void }) | undefined;
    if (source && typeof source.setTiles === 'function') source.setTiles([url]);
    else removeIfPresent(map, FIRE_LAYER, FIRE_SOURCE);
    if (!map.getSource(FIRE_SOURCE)) {
      map.addSource(FIRE_SOURCE, { type: 'raster', tiles: [url], tileSize: 256, maxzoom: 8, attribution: NASA_ATTRIBUTION });
    }
    if (!map.getLayer(FIRE_LAYER)) {
      map.addLayer({ id: FIRE_LAYER, type: 'raster', source: FIRE_SOURCE, paint: { 'raster-opacity': 0.95, 'raster-fade-duration': 0 } }, anchorId(map));
    }
  }
}

export function removeWeatherLayers(map: maplibregl.Map): void {
  syncWeatherLayers(map, null);
}

const HOUR = 3600 * 1000;

// "Sat 10 Oct, 15:00 UTC": the forecast hour, in UTC so it means the same everywhere.
export function formatForecastTime(iso: string): string {
  return `${new Date(iso).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`;
}

// "in 18 h", "6 h ago" or "now", for the gap between a forecast hour and a moment.
export function relativeHours(iso: string, now: number): string {
  const hours = Math.round((Date.parse(iso) - now) / HOUR);
  if (hours === 0) return 'now';
  return hours > 0 ? `in ${hours} h` : `${-hours} h ago`;
}
