"""The single ETA engine (spec 4.3 / 4.4).

simulate_arrival() is the ONLY function that produces arrival-time samples.
Current ETA, risk and every War Room option call it.

It is a Monte Carlo simulation under declared distributions. It is not a
trained ML model and makes no empirical accuracy claim.
"""
from __future__ import annotations

import math

import numpy as np

from .contracts import EngineInputs, EngineResult, Tri
from .variates import VariateMatrix


# ---------- triangular distribution helpers ----------

def tri_cdf(x, t: Tri):
    x = np.asarray(x, dtype=float)
    a, c, b = t.low, t.mode, t.high
    if b - a < 1e-12:
        return np.where(x >= a, 1.0, 0.0)
    left = (x - a) ** 2 / ((b - a) * (c - a)) if c > a else np.zeros_like(x)
    right = 1.0 - (b - x) ** 2 / ((b - a) * (b - c)) if b > c else np.ones_like(x)
    out = np.where(x <= c, left, right)
    return np.clip(np.where(x <= a, 0.0, np.where(x >= b, 1.0, out)), 0.0, 1.0)


def tri_inv(u, t: Tri):
    u = np.asarray(u, dtype=float)
    a, c, b = t.low, t.mode, t.high
    if b - a < 1e-12:
        return np.full_like(u, a)
    fc = (c - a) / (b - a)
    left = a + np.sqrt(np.maximum(u * (b - a) * (c - a), 0.0))
    right = b - np.sqrt(np.maximum((1.0 - u) * (b - a) * (b - c), 0.0))
    return np.where(u < fc, left, right)


def sample_end_rel(u, start_rel_h: float, dur: Tri, floor_h: float):
    """End time (relative hours) of a timed disruption.

    Not yet started: unconditional duration. Already active with elapsed e:
    condition on "still active" using u2 = F(e) + u * (1 - F(e)), so the sampled
    total duration can never imply the disruption already ended.
    """
    if start_rel_h > 0:
        return start_rel_h + tri_inv(u, dur)
    e = -start_rel_h
    fe = float(tri_cdf(e, dur))
    if fe >= 0.999:
        return u * floor_h                      # overdue: short residual from now
    return start_rel_h + tri_inv(fe + u * (1.0 - fe), dur)


def lognormal_factor(z, sigma: float):
    """Mean-one factor: exp(sigma*Z - sigma^2/2). sigma is a standard deviation."""
    return np.exp(sigma * z - 0.5 * sigma * sigma)


def nearest_rank(sorted_samples: np.ndarray, p: float) -> float:
    n = len(sorted_samples)
    return float(sorted_samples[max(1, math.ceil(p * n)) - 1])


# ---------- travel propagation (shared with the truth simulator) ----------

def propagate(depart, base_hours, factors, closures_by_seg, slowdowns_by_seg, skip_closure_first=False):
    """Move N samples along K segments using the entry-time rule.

    depart: (N,) start times. base_hours: (K,). factors: (N,K) multiplicative.
    closures_by_seg[j]: list of (start, end[N]); a closure blocks ENTRY only.
    slowdowns_by_seg[j]: list of (start, end[N], multiplier); applies when the
    vehicle ENTERS j inside the window. Overlaps take the max, never the sum.
    Returns arrive, reach[N,K], enter[N,K], exit[N,K], closure_wait[N], slowdown_inc[N].
    """
    t = np.array(depart, dtype=float)
    n, k = t.shape[0], len(base_hours)
    reach = np.zeros((n, k))
    enter = np.zeros((n, k))
    exit_ = np.zeros((n, k))
    cw_total = np.zeros(n)
    sl_total = np.zeros(n)
    for j in range(k):
        reach[:, j] = t
        cw = np.zeros(n)
        if not (j == 0 and skip_closure_first):
            for start, end in closures_by_seg.get(j, ()):
                cw = np.maximum(cw, np.where(t >= start, np.maximum(0.0, end - t), 0.0))
        t_in = t + cw
        m = np.ones(n)
        for start, end, mult in slowdowns_by_seg.get(j, ()):
            m = np.maximum(m, np.where((t_in >= start) & (t_in < end), mult, 1.0))
        enter[:, j] = t_in
        t = t_in + base_hours[j] * factors[:, j] * m
        exit_[:, j] = t
        cw_total += cw
        sl_total += base_hours[j] * (m - 1.0)
    return t, reach, enter, exit_, cw_total, sl_total


# ---------- the engine ----------

def simulate_arrival(inputs: EngineInputs, n_samples: int, seed: int) -> EngineResult:
    n = int(n_samples)
    vm = VariateMatrix(seed, n)
    lot = inputs.lot_key
    floor = inputs.residual_floor_h

    # handling: only stages not yet completed
    handling = np.zeros(n)
    base_handling = 0.0
    for st in inputs.handling_stages:
        dur = tri_inv(vm.u(f"{lot}handling:{st.name}"), st.dist)
        handling += np.maximum(0.0, dur - st.elapsed_h)
        base_handling += max(0.0, st.ref_hours - st.elapsed_h)

    gate = tri_inv(vm.u(f"{lot}gate"), inputs.gate_queue) if inputs.gate_queue else np.zeros(n)

    repair = np.zeros(n)
    if inputs.repair is not None:
        r = inputs.repair
        repair = np.maximum(0.0, sample_end_rel(vm.u(f"{lot}repair:{r.key}"), -r.elapsed_h, r.duration, floor))

    depart = inputs.planned_wait_h + inputs.dispatch_delay_h + handling + gate + repair

    segs = inputs.segments
    k = len(segs)
    base = np.array([s.base_hours for s in segs], dtype=float)
    s_route = inputs.sigma_route * inputs.sigma_scale
    s_seg = inputs.sigma_segment * inputs.sigma_scale
    factors = np.ones((n, k))
    if k:
        route_f = lognormal_factor(vm.z("route"), s_route)
        for j, s in enumerate(segs):
            factors[:, j] = route_f * lognormal_factor(vm.z(f"seg:{s.key}"), s_seg)

    index = {s.key: j for j, s in enumerate(segs)}
    closures: dict = {}
    for c in inputs.closures:
        if c.segment_key in index:
            end = sample_end_rel(vm.u(f"closure:{c.key}"), c.start_rel_h, c.duration, floor)
            closures.setdefault(index[c.segment_key], []).append((c.start_rel_h, end))
    slowdowns: dict = {}
    for s in inputs.slowdowns:
        if s.segment_key in index:
            end = sample_end_rel(vm.u(f"slowdown:{s.key}"), s.start_rel_h, s.duration, floor)
            slowdowns.setdefault(index[s.segment_key], []).append((s.start_rel_h, end, s.multiplier))

    skip_first = bool(k and segs[0].already_inside)
    arrive, _, _, _, closure_wait, slowdown_inc = propagate(depart, base, factors, closures, slowdowns, skip_first)

    base_travel = float(base.sum())
    baseline = inputs.planned_wait_h + base_handling + base_travel
    mean_t = float(arrive.mean())
    comp = {
        "handling_deviation": float(handling.mean()) - base_handling,
        "gate_queue": float(gate.mean()),
        "dispatch_delay": float(inputs.dispatch_delay_h),
        "slowdown": float(slowdown_inc.mean()),
        "closure_wait": float(closure_wait.mean()),
        "repair_wait": float(repair.mean()),
    }
    # residual closes the decomposition exactly (travel variability + interactions)
    comp["variability"] = mean_t - baseline - sum(comp.values())

    srt = np.sort(arrive)
    d = inputs.promised_rel_h
    return EngineResult(
        samples=arrive, n=n, seed=int(seed),
        p10=nearest_rank(srt, 0.10), p50=nearest_rank(srt, 0.50), p90=nearest_rank(srt, 0.90),
        mean=mean_t, p_late=float((arrive > d).mean()),
        expected_late_hours=float(np.maximum(0.0, arrive - d).mean()),
        baseline_h=baseline, components=comp,
    )
