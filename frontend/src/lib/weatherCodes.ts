// WMO weather interpretation codes, as published by Open-Meteo (a fixed
// standard table, not generated). Unknown codes fall back to a neutral label.
const CODES: Record<number, [label: string, icon: string]> = {
  0: ['Clear sky', '☀️'],
  1: ['Mainly clear', '🌤️'],
  2: ['Partly cloudy', '⛅'],
  3: ['Overcast', '☁️'],
  45: ['Fog', '🌫️'],
  48: ['Rime fog', '🌫️'],
  51: ['Light drizzle', '🌦️'],
  53: ['Drizzle', '🌦️'],
  55: ['Dense drizzle', '🌧️'],
  56: ['Freezing drizzle', '🌧️'],
  57: ['Heavy freezing drizzle', '🌧️'],
  61: ['Light rain', '🌦️'],
  63: ['Rain', '🌧️'],
  65: ['Heavy rain', '🌧️'],
  66: ['Freezing rain', '🌧️'],
  67: ['Heavy freezing rain', '🌧️'],
  71: ['Light snow', '🌨️'],
  73: ['Snow', '🌨️'],
  75: ['Heavy snow', '❄️'],
  77: ['Snow grains', '🌨️'],
  80: ['Light showers', '🌦️'],
  81: ['Showers', '🌧️'],
  82: ['Violent showers', '⛈️'],
  85: ['Light snow showers', '🌨️'],
  86: ['Heavy snow showers', '❄️'],
  95: ['Thunderstorm', '⛈️'],
  96: ['Thunderstorm with hail', '⛈️'],
  99: ['Severe thunderstorm with hail', '⛈️'],
};

export function describeWeather(code: number | null | undefined): { label: string; icon: string } {
  const entry = code == null ? undefined : CODES[code];
  return entry ? { label: entry[0], icon: entry[1] } : { label: 'Unknown', icon: '❔' };
}
