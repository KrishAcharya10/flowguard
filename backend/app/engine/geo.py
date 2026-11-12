"""Geometry helpers. Pure functions."""
from __future__ import annotations

import math
from dataclasses import dataclass


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class PathPoint:
    waypoint_id: str
    name: str
    lat: float
    lon: float
    is_decision_node: bool
    route_id: str            # route that owns the segment STARTING at this point
    speed_kmh: float         # speed on the segment starting here
    km_from_start: float = 0.0


@dataclass(frozen=True)
class PathSegment:
    key: str                 # "<route_id>:<from_waypoint_id>"
    route_id: str
    from_idx: int
    km: float
    speed_kmh: float
    km_start: float

    @property
    def km_end(self) -> float:
        return self.km_start + self.km


def build_segments(points: list[PathPoint], circuity: float) -> tuple[list[PathPoint], list[PathSegment]]:
    """Compute road distances: d = haversine(consecutive waypoints) * circuity."""
    out_pts, segs, km = [], [], 0.0
    for i, p in enumerate(points):
        out_pts.append(PathPoint(p.waypoint_id, p.name, p.lat, p.lon, p.is_decision_node,
                                 p.route_id, p.speed_kmh, km))
        if i + 1 < len(points):
            q = points[i + 1]
            d = haversine_km(p.lat, p.lon, q.lat, q.lon) * circuity
            segs.append(PathSegment(f"{p.route_id}:{p.waypoint_id}", p.route_id, i, d, p.speed_kmh, km))
            km += d
    return out_pts, segs


def position_at_km(points: list[PathPoint], segs: list[PathSegment], km: float) -> tuple[float, float]:
    if not segs or km <= 0:
        return points[0].lat, points[0].lon
    for s in segs:
        if km <= s.km_end:
            f = 0.0 if s.km <= 0 else (km - s.km_start) / s.km
            a, b = points[s.from_idx], points[s.from_idx + 1]
            return a.lat + (b.lat - a.lat) * f, a.lon + (b.lon - a.lon) * f
    return points[-1].lat, points[-1].lon
