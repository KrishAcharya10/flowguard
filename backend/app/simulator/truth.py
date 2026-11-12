"""Hidden simulator truth (spec 4.2).

Realisations are derived from seed_truth on demand and NEVER stored. They cover
the primary route, the alternative route and split lots, so the outcome of any
approved option is already determined. The prediction engine and the mapping
layer never import this module; nothing here is exposed by the API.
"""
from __future__ import annotations

import zlib
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import Assumptions
from ..engine.contracts import Tri
from ..engine.eta import lognormal_factor, tri_inv
from ..seeds import seed_truth, seed_truth_disruption
from ..services.core import hours, plus_hours
from ..services.paths import get_path


def _rng(seed: int, name: str) -> np.random.Generator:
    return np.random.default_rng([seed & 0xFFFFFFFF, zlib.crc32(name.encode()) & 0xFFFFFFFF])


def _u(seed: int, name: str) -> float:
    return float(_rng(seed, "u|" + name).random())


def _z(seed: int, name: str) -> float:
    return float(_rng(seed, "z|" + name).standard_normal())


def disruption_true_duration_h(global_seed: int, d: m.Disruption) -> float:
    u = _u(seed_truth_disruption(global_seed, d.id), "duration")
    return float(tri_inv(np.array([u]), Tri(d.dur_min_h, d.dur_mode_h, d.dur_max_h))[0])


def disruption_true_end(global_seed: int, d: m.Disruption) -> datetime:
    if d.status == "ENDED" and d.ended_at is not None:
        return d.ended_at
    return plus_hours(d.start_at, disruption_true_duration_h(global_seed, d))


def _window_mult(global_seed: int, all_d: list[m.Disruption], kind: str, at: datetime) -> float:
    mult = 1.0
    for d in all_d:
        if d.kind == kind and d.start_at <= at < disruption_true_end(global_seed, d):
            mult = max(mult, d.multiplier)
    return mult


def loading_true_h(global_seed: int, sh: m.Shipment, a: Assumptions, all_d: list[m.Disruption]) -> float:
    seed = seed_truth(global_seed, sh.id, sh.route_id, sh.lot_type)
    mult = _window_mult(global_seed, all_d, "HANDLING_SHIFT", sh.state_entered_at)
    tri = Tri(a.loading_min_h, a.loading_mode_h, a.loading_max_h).scaled(mult)
    return float(tri_inv(np.array([_u(seed, "loading")]), tri)[0])


def gate_true_h(global_seed: int, sh: m.Shipment, a: Assumptions, all_d: list[m.Disruption]) -> float:
    seed = seed_truth(global_seed, sh.id, sh.route_id, sh.lot_type)
    mult = _window_mult(global_seed, all_d, "GATE_QUEUE_SHIFT", sh.state_entered_at)
    tri = Tri(a.gate_min_h, a.gate_mode_h, a.gate_max_h).scaled(mult)
    return float(tri_inv(np.array([_u(seed, "gate")]), tri)[0])


def transit_timeline(db: Session, global_seed: int, sh: m.Shipment, a: Assumptions,
                     all_d: list[m.Disruption]) -> list[tuple[float, float]]:
    """Piecewise-linear (hours since departure, km along path) for an IN_TRANSIT shipment.

    Same road rules as the predictor: a closure blocks ENTRY only; a slowdown applies
    to a segment entered inside its window. Breakdowns pause the vehicle where it is.
    """
    _, segs = get_path(db, sh.route_id, sh.active_alternative_route_id)
    transporter = db.get(m.Transporter, sh.transporter_id)
    s_route = a.sigma_route * transporter.sigma_factor
    s_seg = a.sigma_segment * transporter.sigma_factor
    t0 = sh.departed_at
    factors = []
    for s in segs:
        seed = seed_truth(global_seed, sh.id, s.route_id, sh.lot_type)   # per-route realisation
        factors.append(float(lognormal_factor(_z(seed, "route"), s_route) * lognormal_factor(_z(seed, "seg:" + s.key), s_seg)))
    closures: dict[int, list] = {}
    slowdowns: dict[int, list] = {}
    cuts: list[tuple[float, float]] = []
    index = {s.key: j for j, s in enumerate(segs)}
    for d in all_d:
        start, end = hours(d.start_at - t0), hours(disruption_true_end(global_seed, d) - t0)
        key = f"{d.route_id}:{d.segment_waypoint_id}"
        if d.kind == "CLOSURE" and key in index:
            closures.setdefault(index[key], []).append((start, end))
        elif d.kind == "SLOWDOWN" and key in index:
            slowdowns.setdefault(index[key], []).append((start, end, d.multiplier))
            cuts += [(start, 0.0), (end, 0.0)]              # re-evaluate the slowdown at its boundaries
        elif d.kind == "VEHICLE_STOPPAGE" and d.shipment_id == sh.id:
            cuts.append((start, max(0.0, end - start)))
    cuts.sort()

    points: list[tuple[float, float]] = [(0.0, 0.0)]
    t, km = 0.0, 0.0
    while True:
        leg = [(t, km)]
        lt, inside = t, False
        for j, s in enumerate(segs):
            if km >= s.km_end - 1e-9:
                continue
            start_km = max(km, s.km_start)
            inside = start_km > s.km_start + 1e-9
            wait = 0.0
            if not inside:
                for c_start, c_end in closures.get(j, ()):
                    if lt >= c_start:
                        wait = max(wait, max(0.0, c_end - lt))
            if wait > 0:
                lt += wait
                leg.append((lt, start_km))
            mult = 1.0
            for s_start, s_end, s_mult in slowdowns.get(j, ()):
                if s_start <= lt < s_end:
                    mult = max(mult, s_mult)
            lt += (s.km_end - start_km) / s.speed_kmh * factors[j] * mult
            leg.append((lt, s.km_end))
            km = s.km_end
        cut = next(((ct, pause) for ct, pause in cuts if t < ct < leg[-1][0]), None)
        if cut is None:
            points += leg[1:]
            return points
        ct, pause = cut
        kept = [p for p in leg if p[0] <= ct]
        km_c = position_km(leg, ct)
        points += kept[1:] + [(ct, km_c)]
        if pause > 0:
            points.append((ct + pause, km_c))
        cuts = [c for c in cuts if c[0] > ct]
        t, km = ct + pause, km_c


def position_km(points: list[tuple[float, float]], t: float) -> float:
    if t <= points[0][0]:
        return points[0][1]
    for (t0, k0), (t1, k1) in zip(points, points[1:]):
        if t <= t1:
            return k0 if t1 - t0 < 1e-12 else k0 + (k1 - k0) * (t - t0) / (t1 - t0)
    return points[-1][1]
