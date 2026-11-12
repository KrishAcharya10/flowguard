"""War Room maths (spec 4.8): option metrics, costs, hard constraints,
recommendation and 16-case stability. Pure functions; numpy only.

Single-shipment decision support. This is NOT fleet optimisation.
"""
from __future__ import annotations

import dataclasses
import itertools
from typing import Optional

import numpy as np

from .contracts import Constraints, CostParams, EngineInputs, OptionSpec, StockParams
from .eta import nearest_rank, simulate_arrival
from .stock import stockout_hours

REC_NJI = "NO_JUSTIFIED_INTERVENTION"
REC_NONE = "NO_FEASIBLE_OPTION"
STRESS = (0.75, 1.25)


def scale_durations(inputs: EngineInputs, k: float) -> EngineInputs:
    """Scale every disruption duration by k (used by the stability stress)."""
    return dataclasses.replace(
        inputs,
        closures=tuple(dataclasses.replace(c, duration=c.duration.scaled(k)) for c in inputs.closures),
        slowdowns=tuple(dataclasses.replace(s, duration=s.duration.scaled(k)) for s in inputs.slowdowns),
        repair=dataclasses.replace(inputs.repair, duration=inputs.repair.duration.scaled(k)) if inputs.repair else None,
    )


def raw_metrics(spec: OptionSpec, stock: Optional[StockParams], n: int, seed: int,
                duration_scale: float = 1.0) -> dict:
    """Run the engine for every lot of one option. Cost-free quantities only."""
    if not spec.eligible:
        return {"code": spec.code, "eligible": False, "ineligible_reason": spec.ineligible_reason}
    lots = []
    total_q = sum(l.quantity_t for l in spec.lots)
    d = spec.lots[0].inputs.promised_rel_h
    late_weighted = 0.0
    samples = []
    for lot in spec.lots:
        inp = lot.inputs if duration_scale == 1.0 else scale_durations(lot.inputs, duration_scale)
        res = simulate_arrival(inp, n, seed)
        samples.append((res.samples, lot.quantity_t))
        late_weighted += (lot.quantity_t / total_q) * res.expected_late_hours
        lots.append({"lot_type": lot.lot_type, "quantity_t": lot.quantity_t, "p10": res.p10,
                     "p50": res.p50, "p90": res.p90, "p_late": res.p_late, "mean": res.mean,
                     "components": res.components, "baseline_h": res.baseline_h})
    complete = np.max(np.stack([s for s, _ in samples], axis=1), axis=1)   # order complete = last lot
    srt = np.sort(complete)
    out = {
        "code": spec.code, "eligible": True, "ineligible_reason": "",
        "lots": lots, "extra_km": spec.extra_km, "freight_base": spec.freight_rs,
        "p50": nearest_rank(srt, 0.5), "p90": nearest_rank(srt, 0.9),
        "p_late": float((complete > d).mean()),
        "exp_late_h": late_weighted,                 # quantity-weighted (split SLA formula)
        "p_stockout": None, "exp_stockout_h": None, "p_priority_ok": None,
        "urgent_qty_t": next((l.quantity_t for l in spec.lots if l.lot_type == "URGENT"), None),
    }
    if stock is not None:
        so = stockout_hours(samples, stock)
        out["p_stockout"] = float((so > 0).mean())
        out["exp_stockout_h"] = float(so.mean())
        first = samples[0][0]                       # SINGLE or URGENT lot
        out["p_priority_ok"] = float((first + stock.unload_h <= stock.depletion_rel_h).mean())
    return out


def apply_costs(raw: dict, costs: CostParams) -> dict:
    """Freight + SLA + stock-out, each shown separately. Linear in freight scale, p and s."""
    if not raw["eligible"]:
        return dict(raw)
    m = dict(raw)
    m["freight"] = raw["freight_base"] * costs.freight_scale
    m["sla_cost"] = costs.sla_per_late_hour * raw["exp_late_h"]
    m["stockout_cost"] = costs.stockout_per_hour * (raw["exp_stockout_h"] or 0.0)
    m["total"] = m["freight"] + m["sla_cost"] + m["stockout_cost"]
    return m


def violations(m: dict, c: Constraints) -> list[dict]:
    v = []
    if m["p_stockout"] is not None and m["p_stockout"] > c.alpha + 1e-12:
        v.append({"constraint": "MAX_P_STOCKOUT", "value": m["p_stockout"], "limit": c.alpha,
                  "text": f"P(stock-out) {m['p_stockout']:.0%} exceeds the limit {c.alpha:.0%}"})
    if m["p_priority_ok"] is not None and m["p_priority_ok"] < 1 - c.alpha - 1e-12 and m["code"] == "SPLIT":
        v.append({"constraint": "PRIORITY_ARRIVAL", "value": m["p_priority_ok"], "limit": 1 - c.alpha,
                  "text": f"P(urgent lot usable before stock runs out) {m['p_priority_ok']:.0%} is below {1 - c.alpha:.0%}"})
    if c.max_freight_rs is not None and m["freight"] > c.max_freight_rs + 1e-9:
        v.append({"constraint": "MAX_FREIGHT", "value": m["freight"], "limit": c.max_freight_rs,
                  "text": f"Incremental freight Rs {m['freight']:,.0f} exceeds the cap Rs {c.max_freight_rs:,.0f}"})
    if m["urgent_qty_t"] is not None and m["urgent_qty_t"] < c.min_urgent_qty_t - 1e-9:
        v.append({"constraint": "MIN_URGENT_QTY", "value": m["urgent_qty_t"], "limit": c.min_urgent_qty_t,
                  "text": f"Urgent lot {m['urgent_qty_t']:.1f} t is below the minimum {c.min_urgent_qty_t:.1f} t"})
    if c.beta is not None and m["p_late"] > c.beta + 1e-12:
        v.append({"constraint": "MAX_P_LATE", "value": m["p_late"], "limit": c.beta,
                  "text": f"P(late) {m['p_late']:.0%} exceeds the limit {c.beta:.0%}"})
    return v


def _violation_score(v: list[dict]) -> float:
    s = 0.0
    for x in v:
        lim = abs(x["limit"]) if abs(x["limit"]) > 1e-9 else 1.0
        s += abs(x["value"] - x["limit"]) / lim
    return s


def recommend(options: list[dict], c: Constraints) -> dict:
    """Lowest expected total among feasible options, with a tie-break in favour of Continue."""
    elig = [o for o in options if o["eligible"]]
    feas = [o for o in elig if o["feasible"]]
    cont = next(o for o in options if o["code"] == "CONTINUE")
    if not feas:
        least = min(elig, key=lambda o: _violation_score(o["violations"]))
        return {"code": REC_NONE, "banner": "NO FEASIBLE OPTION - ESCALATE", "option_code": None,
                "least_violating_code": least["code"], "saving_vs_continue": None, "threshold": None}
    best = min(feas, key=lambda o: o["total"])
    threshold = max(c.tie_pct * cont["total"], c.tie_min_abs_rs)   # zero baseline -> min absolute saving
    saving = cont["total"] - best["total"]
    if cont["feasible"] and (best["code"] == "CONTINUE" or saving < threshold):
        return {"code": REC_NJI, "banner": "NO JUSTIFIED INTERVENTION - CONTINUE CURRENT PLAN",
                "option_code": "CONTINUE", "least_violating_code": None,
                "saving_vs_continue": saving, "threshold": threshold}
    return {"code": best["code"], "banner": f"RECOMMENDED: {best['code']}", "option_code": best["code"],
            "least_violating_code": None, "saving_vs_continue": saving, "threshold": threshold}


def _decide(raws: list[dict], costs: CostParams, c: Constraints):
    opts = []
    for r in raws:
        m = apply_costs(r, costs)
        if m["eligible"]:
            m["violations"] = violations(m, c)
            m["feasible"] = not m["violations"]
        else:
            m["violations"], m["feasible"] = [], False
        opts.append(m)
    return opts, recommend(opts, c)


def _break_even(opts: list[dict], rec_code: str, costs: CostParams) -> Optional[dict]:
    """Scale at which the recommended option ties with Continue on expected total.
    Totals are linear in freight scale, p and s. Cost ordering only, not feasibility."""
    if rec_code in (REC_NJI, REC_NONE, "CONTINUE"):
        return None
    k = next(o for o in opts if o["code"] == rec_code)
    c0 = next(o for o in opts if o["code"] == "CONTINUE")
    out = {}
    if k["freight"] > 0:
        out["freight"] = (c0["total"] - k["sla_cost"] - k["stockout_cost"]) / k["freight"]
    d_sla = c0["sla_cost"] - k["sla_cost"]
    if abs(d_sla) > 1e-9:
        out["sla_rate"] = (k["freight"] + k["stockout_cost"] - c0["stockout_cost"]) / d_sla
    d_so = c0["stockout_cost"] - k["stockout_cost"]
    if abs(d_so) > 1e-9:
        out["stockout_rate"] = (k["freight"] + k["sla_cost"] - c0["sla_cost"]) / d_so
    out = {n: v for n, v in out.items() if v > 0}
    if not out:
        return None
    nearest = min(out, key=lambda n: abs(np.log(out[n])))
    return {"multipliers": out, "nearest": nearest, "nearest_multiplier": out[nearest]}


def evaluate_case(specs: list[OptionSpec], stock: Optional[StockParams], costs: CostParams,
                  c: Constraints, n: int, seed: int, with_stability: bool = True) -> dict:
    """All options on the SAME seed (common random numbers), then the decision."""
    raws = [raw_metrics(s, stock, n, seed) for s in specs]
    opts, rec = _decide(raws, costs, c)
    out = {"options": opts, "recommendation": rec, "stability": None, "n": n, "seed": seed}
    if not with_stability:
        return out
    # duration changes rerun the engine (same variates); cost-only changes reuse samples
    raws_by_dur = {k: [raw_metrics(s, stock, n, seed, duration_scale=k) for s in specs] for k in STRESS}
    cases, holds = [], 0
    for fs, ps, ss, ds in itertools.product(STRESS, STRESS, STRESS, STRESS):
        stressed = CostParams(costs.sla_per_late_hour * ps, costs.stockout_per_hour * ss, costs.freight_scale * fs)
        _, r = _decide(raws_by_dur[ds], stressed, c)
        same = r["code"] == rec["code"]
        holds += int(same)
        cases.append({"freight": fs, "sla_rate": ps, "stockout_rate": ss, "duration": ds,
                      "recommendation": r["code"], "same": same})
    if rec["code"] == REC_NONE or holds < 8:
        label = "NO ROBUST RECOMMENDATION"
    elif holds == 16:
        label = "STABLE"
    else:
        label = "SENSITIVE"
    out["stability"] = {"label": label, "holds": holds, "total": 16, "cases": cases,
                        "break_even": _break_even(opts, rec["code"], costs)}
    return out
