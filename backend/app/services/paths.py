"""Route geometry from the database. Connectivity is explicit, never inferred from names."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from ..engine.geo import PathPoint, PathSegment, build_segments

_cache: dict = {}


def clear_cache() -> None:
    _cache.clear()


def _waypoints(db: Session, route_id: str) -> list[m.RouteWaypoint]:
    return (db.query(m.RouteWaypoint).filter(m.RouteWaypoint.route_id == route_id)
            .order_by(m.RouteWaypoint.sequence).all())


def _pt(w: m.RouteWaypoint) -> PathPoint:
    return PathPoint(w.id, w.name, w.lat, w.lon, w.is_decision_node, w.route_id, w.speed_kmh_to_next)


def alternative_topology(db: Session, alt: m.Route) -> tuple[Optional[int], Optional[int], str]:
    """Return (entry index, rejoin index) on the primary route, or a reason it is invalid."""
    prim = _waypoints(db, alt.alternative_of_route_id) if alt.alternative_of_route_id else []
    ids = [w.id for w in prim]
    e, r = alt.alternative_entry_decision_node_id, alt.alternative_rejoin_waypoint_id
    if not e or not r or e not in ids or r not in ids:
        return None, None, "No valid connection: the alternative route does not name an entry node and rejoin point on this route"
    ei, ri = ids.index(e), ids.index(r)
    if not prim[ei].is_decision_node:
        return None, None, "No valid connection: the entry point is not a decision node"
    if ri <= ei:
        return None, None, "No valid connection: the rejoin point is not after the entry node"
    return ei, ri, ""


def get_path(db: Session, route_id: str, alt_route_id: Optional[str] = None) -> tuple[list[PathPoint], list[PathSegment]]:
    """Primary path, or primary-to-entry + alternative + rejoin-to-destination."""
    key = (route_id, alt_route_id)
    if key in _cache:
        return _cache[key]
    route = db.get(m.Route, route_id)
    prim = [_pt(w) for w in _waypoints(db, route_id)]
    if alt_route_id:
        alt = db.get(m.Route, alt_route_id)
        ei, ri, why = alternative_topology(db, alt)
        if ei is None or alt.alternative_of_route_id != route_id:
            raise ValueError(why or "alternative does not belong to this route")
        alt_pts = [_pt(w) for w in _waypoints(db, alt_route_id)]
        pts = prim[:ei] + alt_pts[:-1] + prim[ri:]
    else:
        pts = prim
    out = build_segments(pts, route.road_circuity_factor)
    _cache[key] = out
    return out


def entry_km(db: Session, route_id: str, alt: m.Route) -> float:
    """Distance from the plant to the alternative's entry decision node."""
    pts, _ = get_path(db, route_id)
    ei, _, _ = alternative_topology(db, alt)
    return pts[ei].km_from_start


def total_km(segs: list[PathSegment]) -> float:
    return segs[-1].km_end if segs else 0.0
