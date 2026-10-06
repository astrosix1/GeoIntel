// Where the sun is, worked out from the date alone with the standard NOAA solar-position equations
// (accurate to about a minute for sunrise and sunset). No network and no library. This file imports
// nothing so it can be unit-tested directly (frontend/tests/sun.test.ts).

const RAD = Math.PI / 180;
const DEG = 180 / Math.PI;
const DAY_MS = 86_400_000;
const MIN_MS = 60_000;
// The sun counts as risen when its centre is 0.833 degrees below the horizon (its edge plus refraction).
const SUNRISE_ALTITUDE_COSINE = Math.cos(90.833 * RAD);
const TERMINATOR_STEP_DEGREES = 2;

export interface SunPosition {
  // Latitude of the point directly under the sun, in degrees.
  declination: number;
  // How far apparent solar time runs ahead of mean time, in minutes.
  equationOfTime: number;
}

function julianCenturies(date: Date): number {
  const jd = date.getTime() / DAY_MS + 2440587.5;
  return (jd - 2451545) / 36525;
}

export function sunPosition(date: Date): SunPosition {
  const t = julianCenturies(date);
  const l0 = (((280.46646 + t * (36000.76983 + t * 0.0003032)) % 360) + 360) % 360;
  const m = 357.52911 + t * (35999.05029 - 0.0001537 * t);
  const e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
  const mr = m * RAD;
  const c =
    Math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t)) +
    Math.sin(2 * mr) * (0.019993 - 0.000101 * t) +
    Math.sin(3 * mr) * 0.000289;
  const trueLongitude = l0 + c;
  const omega = 125.04 - 1934.136 * t;
  const apparentLongitude = trueLongitude - 0.00569 - 0.00478 * Math.sin(omega * RAD);
  const meanObliquity = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60;
  const obliquity = meanObliquity + 0.00256 * Math.cos(omega * RAD);
  const declination = Math.asin(Math.sin(obliquity * RAD) * Math.sin(apparentLongitude * RAD)) * DEG;
  const y = Math.tan((obliquity * RAD) / 2) ** 2;
  const l0r = l0 * RAD;
  const equationOfTime =
    4 *
    DEG *
    (y * Math.sin(2 * l0r) -
      2 * e * Math.sin(mr) +
      4 * e * y * Math.sin(mr) * Math.cos(2 * l0r) -
      0.5 * y * y * Math.sin(4 * l0r) -
      1.25 * e * e * Math.sin(2 * mr));
  return { declination, equationOfTime };
}

function wrapLongitude(lon: number): number {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

function utcMinutes(date: Date): number {
  return date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60 + date.getUTCMilliseconds() / 60000;
}

// The point on Earth where the sun is directly overhead.
export function subsolarPoint(date: Date): { lat: number; lon: number } {
  const { declination, equationOfTime } = sunPosition(date);
  return { lat: declination, lon: wrapLongitude(-(utcMinutes(date) - 720) / 4 - equationOfTime / 4) };
}

// Height of the sun above the horizon in degrees (negative when it is below).
export function sunAltitude(lat: number, lon: number, date: Date): number {
  const { declination, equationOfTime } = sunPosition(date);
  const hourAngle = (utcMinutes(date) + equationOfTime + 4 * lon) / 4 - 180;
  const sinAlt =
    Math.sin(lat * RAD) * Math.sin(declination * RAD) +
    Math.cos(lat * RAD) * Math.cos(declination * RAD) * Math.cos(hourAngle * RAD);
  return Math.asin(Math.max(-1, Math.min(1, sinAlt))) * DEG;
}

export interface SunTimes {
  // 'polar-day': the sun does not set; 'polar-night': it does not rise.
  status: 'normal' | 'polar-day' | 'polar-night';
  sunrise: Date | null;
  sunset: Date | null;
  solarNoon: Date;
  // Hours of daylight (0 to 24).
  dayLengthHours: number;
}

// Sunrise, sunset and day length for the solar day at (lat, lon) that contains `around`.
export function sunTimes(lat: number, lon: number, around: Date): SunTimes {
  // The local mean solar day containing the instant starts when local mean time is midnight.
  const lonMs = lon * 4 * MIN_MS;
  const dayStart = Math.floor((around.getTime() + lonMs) / DAY_MS) * DAY_MS - lonMs;
  const { declination, equationOfTime } = sunPosition(new Date(dayStart + DAY_MS / 2));
  const solarNoon = new Date(dayStart + DAY_MS / 2 - equationOfTime * MIN_MS);
  const cosH =
    (SUNRISE_ALTITUDE_COSINE - Math.sin(lat * RAD) * Math.sin(declination * RAD)) /
    (Math.cos(lat * RAD) * Math.cos(declination * RAD));
  if (cosH > 1) return { status: 'polar-night', sunrise: null, sunset: null, solarNoon, dayLengthHours: 0 };
  if (cosH < -1) return { status: 'polar-day', sunrise: null, sunset: null, solarNoon, dayLengthHours: 24 };
  const halfDayMs = Math.acos(cosH) * DEG * 4 * MIN_MS;
  return {
    status: 'normal',
    sunrise: new Date(solarNoon.getTime() - halfDayMs),
    sunset: new Date(solarNoon.getTime() + halfDayMs),
    solarNoon,
    dayLengthHours: (2 * halfDayMs) / 3_600_000,
  };
}

type Ring = [number, number][];

// The line where the sun is on the horizon, west to east, as [lon, lat] points.
export function terminatorLine(date: Date): Ring {
  const sub = subsolarPoint(date);
  // Exactly on the equinox the terminator is a meridian; nudge to avoid dividing by zero.
  const tanDecl = Math.tan((Math.abs(sub.lat) < 0.001 ? 0.001 : sub.lat) * RAD);
  const points: Ring = [];
  for (let lon = -180; lon <= 180; lon += TERMINATOR_STEP_DEGREES) {
    const hourAngle = (lon - sub.lon) * RAD;
    points.push([lon, Math.atan(-Math.cos(hourAngle) / tanDecl) * DEG]);
  }
  return points;
}

// The night side of the Earth as a polygon ring (closed), bounded by the terminator and the pole in darkness.
export function nightRing(date: Date): Ring {
  const line = terminatorLine(date);
  const northNight = subsolarPoint(date).lat < 0;     // sun over the southern hemisphere: the north pole is dark
  const poleLat = northNight ? 90 : -90;
  return [...line, [180, poleLat], [-180, poleLat], line[0]];
}
