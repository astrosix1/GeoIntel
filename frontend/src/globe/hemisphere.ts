// Real spherical-geometry check for MapLibre globe-projection markers.
//
// MapLibre `Marker`s are plain screen-projected DOM elements — on a globe
// projection they are NOT occluded by the sphere itself, so a marker whose
// real lat/lon is on the far hemisphere (behind the globe from the camera's
// current facing direction) renders on top of the globe's own correctly-
// occluded surface, as if the globe were transparent. This computes the
// real great-circle angular distance (central angle) between the map's
// current center point and a marker's coordinate via the spherical law of
// cosines (equivalent to, and numerically safer at small angles than, the
// haversine formula — both are exact on a sphere, no small-angle
// approximation). A point is on the far hemisphere once that central angle
// exceeds 90 degrees.

const DEG2RAD = Math.PI / 180;

/**
 * Great-circle central angle (in degrees) between two [lng, lat] points.
 * Correct at the poles (lat = ±90) and across the antimeridian (lng = ±180)
 * because it operates on lat/lng only through trig functions — there is no
 * naive linear-difference term that would need antimeridian unwrapping.
 */
export function angularDistanceDeg(
  a: [number, number],
  b: [number, number],
): number {
  const [lngA, latA] = a;
  const [lngB, latB] = b;

  const phi1 = latA * DEG2RAD;
  const phi2 = latB * DEG2RAD;
  const deltaLambda = (lngB - lngA) * DEG2RAD;

  // Spherical law of cosines. Clamp to [-1, 1] to guard against floating
  // point drift pushing the cosine argument a hair outside its valid range
  // (which would otherwise make Math.acos return NaN) — this happens most
  // often exactly at the poles / for near-identical points, which is
  // precisely the edge case we need to be correct for.
  const cosC =
    Math.sin(phi1) * Math.sin(phi2) +
    Math.cos(phi1) * Math.cos(phi2) * Math.cos(deltaLambda);
  const clamped = Math.max(-1, Math.min(1, cosC));

  return Math.acos(clamped) / DEG2RAD;
}

/**
 * True if [lng, lat] is on the near hemisphere relative to the map's
 * current center (i.e. the great-circle angle between them is <= 90deg).
 */
export function isOnNearHemisphere(
  center: [number, number],
  point: [number, number],
): boolean {
  return angularDistanceDeg(center, point) <= 90;
}
