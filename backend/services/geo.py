"""Small geography helpers."""
import math

EARTH_RADIUS_KM = 6371.0088


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle (haversine) distance between two points, in kilometres.
    Correct across the antimeridian and at the poles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))
