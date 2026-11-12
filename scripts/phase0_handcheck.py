"""Phase 0 hand-check: are the G1, G2 and G3 targets mutually compatible?

Builds the golden inputs BY HAND from the fictional network (no database, no
API) and runs the real engine functions. Prints every target with PASS/FAIL.
Target ranges come from docs/GOLDEN_SCENARIO.md and are never edited here.

Run:  backend/.venv/Scripts/python scripts/phase0_handcheck.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.assumptions import PRESETS, Assumptions  # noqa: E402
from app.engine.contracts import (ClosureInput, Constraints, CostParams, EngineInputs,  # noqa: E402
                                  HandlingStage, LotSpec, OptionSpec, SegmentInput, StockParams, Tri)
from app.engine.eta import simulate_arrival  # noqa: E402
from app.engine.geo import PathPoint, build_segments  # noqa: E402
from app.engine.risk import risk_category, risk_index  # noqa: E402
from app.engine.stock import stockout_hours  # noqa: E402
from app.engine.warroom import evaluate_case  # noqa: E402
from app.seed.network import CIRCUITY, ROUTES  # noqa: E402
from app.seeds import seed_pred  # noqa: E402

A = Assumptions()
GLOBAL_SEED = 20261116
SEED = seed_pred(GLOBAL_SEED, "SHP-PTH-1116-01")
N = A.n_samples
FAILS = []


def check(name, ok, detail):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        FAILS.append(name)


def path(route_id, wps):
    pts = [PathPoint(w[0], w[1], w[2], w[3], w[4], route_id, w[5]) for w in wps]
    return build_segments(pts, CIRCUITY)


# ---- geometry -------------------------------------------------------------
r1_pts, r1 = path("R1", ROUTES["R1"]["waypoints"])
_, r1a = path("R1A", ROUTES["R1A"]["waypoints"])
prim = [SegmentInput(s.key, s.km, s.speed_kmh) for s in r1]
# reroute path: primary to the entry node (W1), bypass, primary from the rejoin (W4)
rer = [prim[0]] + [SegmentInput(s.key, s.km, s.speed_kmh) for s in r1a] + [prim[4]]
km_prim, km_rer = sum(s.km for s in prim), sum(s.km for s in rer)
extra_km = km_rer - km_prim
print(f"R1 primary {km_prim:.1f} km, base {sum(s.base_hours for s in prim):.2f} h; "
      f"reroute {km_rer:.1f} km, base {sum(s.base_hours for s in rer):.2f} h; extra {extra_km:.1f} km")

# ---- G1 inputs (AT_PLANT_GATE at t_now = 0) -------------------------------
D = 11.0                                    # promised_at, hours after t_now
gate = Tri(A.gate_min_h, A.gate_mode_h, A.gate_max_h)
flood = PRESETS["FLOOD_R1"]
closure = ClosureInput("flood", "R1:R1-W2", 0.0, Tri(*flood["duration"]))
Q, RATE, UNLOAD, I0 = 24.0, 2.0, 0.5, 25.0  # tonnes, t/h, h, tonnes
stock_g1 = StockParams(depletion_rel_h=I0 / RATE, rate_tph=RATE, unload_h=UNLOAD)
P_G1, P_G2, S_RATE = 20000.0, 2500.0, A.stockout_cost_per_hour_rs


def inputs(segs, closures=(), lot="", lead=0.0, with_loading=False):
    stages = (HandlingStage("loading", A.loading_ref_h, Tri(A.loading_min_h, A.loading_mode_h, A.loading_max_h)),) \
        if with_loading else ()
    return EngineInputs(segments=tuple(segs), promised_rel_h=D, handling_stages=stages, gate_queue=gate,
                        dispatch_delay_h=lead, closures=tuple(closures), sigma_route=A.sigma_route,
                        sigma_segment=A.sigma_segment, lot_key=lot, residual_floor_h=A.residual_floor_h)


def specs():
    q_u = min(Q, max(A.min_urgent_qty_t, RATE * A.split_cover_hours))
    lead = A.second_vehicle_lead_h
    return [
        OptionSpec("CONTINUE", True, lots=(LotSpec("SINGLE", Q, inputs(prim, [closure])),)),
        OptionSpec("REROUTE", True, lots=(LotSpec("SINGLE", Q, inputs(rer, [closure])),),
                   freight_rs=extra_km * 55.0 + A.reroute_fixed_rs, extra_km=extra_km),
        OptionSpec("SPLIT", True, lots=(
            LotSpec("URGENT", q_u, inputs(rer, [closure], "lot:URGENT|", lead, True)),
            LotSpec("REMAINDER", Q - q_u, inputs(prim, [closure], "lot:REMAINDER|", lead, True))),
            freight_rs=A.second_vehicle_fixed_rs + 55.0 * km_rer, extra_km=km_rer),
    ]


def show(case):
    for o in case["options"]:
        ps = "n/a" if o["p_stockout"] is None else f"{o['p_stockout']:.1%}"
        print(f"    {o['code']:<9} P50 {o['p50']:.2f}h P90 {o['p90']:.2f}h P(late) {o['p_late']:.1%} "
              f"P(stockout) {ps} freight {o['freight']:,.0f} SLA {o['sla_cost']:,.0f} "
              f"stock {o['stockout_cost']:,.0f} total {o['total']:,.0f} feasible={o['feasible']}")
        for v in o["violations"]:
            print(f"        violates: {v['text']}")
    print(f"    -> {case['recommendation']['banner']}"
          + (f" | stability {case['stability']['label']} {case['stability']['holds']}/16" if case["stability"] else ""))


print("\nStock relation: S - u >= D so a stock-out implies lateness")
check("S about 1-2 h after D", 1.0 <= stock_g1.depletion_rel_h - D <= 2.0, f"S - D = {stock_g1.depletion_rel_h - D:.2f} h")
check("u <= 1 h and S - u >= D", UNLOAD <= 1 and stock_g1.depletion_rel_h - UNLOAD >= D,
      f"S - u = {stock_g1.depletion_rel_h - UNLOAD:.2f} >= D = {D}")

print("\nG1 before injection")
b = simulate_arrival(inputs(prim), N, SEED)
pso = float((stockout_hours([(b.samples, Q)], stock_g1) > 0).mean())
idx = risk_index(b.p_late, pso, A.w_late, A.w_stock)
check("P(late) <= 15%", b.p_late <= 0.15, f"{b.p_late:.1%} (P50 {b.p50:.2f} h, P90 {b.p90:.2f} h)")
check("P(stockout) <= 5%", pso <= 0.05, f"{pso:.1%}")
check("category LOW", risk_category(idx, b.p_late, pso) == "LOW", f"index {idx}")

print("\nG1 after flooding (alpha = 10%)")
c_g1 = Constraints(alpha=A.alpha, min_urgent_qty_t=A.min_urgent_qty_t, tie_pct=A.tie_pct, tie_min_abs_rs=A.tie_min_abs_rs)
g1 = evaluate_case(specs(), stock_g1, CostParams(P_G1, S_RATE), c_g1, N, SEED)
show(g1)
cont, rr, sp = g1["options"]
cidx = risk_index(cont["p_late"], cont["p_stockout"], A.w_late, A.w_stock)
check("Continue P(late) >= 70%", cont["p_late"] >= 0.70, f"{cont['p_late']:.1%}")
check("Continue P(stockout) >= 30%", cont["p_stockout"] >= 0.30, f"{cont['p_stockout']:.1%}")
check("Continue category HIGH", risk_category(cidx, cont["p_late"], cont["p_stockout"]) == "HIGH", f"index {cidx}")
check("Continue P50 2-4 h after D", 2.0 <= cont["p50"] - D <= 4.0, f"P50 - D = {cont['p50'] - D:.2f} h")
check("Reroute P(late) <= 30%", rr["p_late"] <= 0.30, f"{rr['p_late']:.1%}")
check("Reroute P(stockout) in 2-8%", 0.02 <= rr["p_stockout"] <= 0.08, f"{rr['p_stockout']:.1%}")
check("Reroute freight > 0", rr["freight"] > 0, f"Rs {rr['freight']:,.0f}")
check("Total_Reroute <= 0.6 x Total_Continue", rr["total"] <= 0.6 * cont["total"],
      f"{rr['total']:,.0f} vs 0.6 x {cont['total']:,.0f} = {0.6 * cont['total']:,.0f}")
check("Split eligible", sp["eligible"], "eligible while AT_PLANT_GATE")
check("Split freight > Reroute freight", sp["freight"] > rr["freight"], f"{sp['freight']:,.0f} > {rr['freight']:,.0f}")
check("Recommendation REROUTE", g1["recommendation"]["code"] == "REROUTE", g1["recommendation"]["banner"])
check("Stability STABLE 16/16", g1["stability"]["label"] == "STABLE" and g1["stability"]["holds"] == 16,
      f"{g1['stability']['label']} {g1['stability']['holds']}/16")

print("\nG2 same flooding, high stock cover (120 t at 1.5 t/h), low SLA rate")
stock_g2 = StockParams(depletion_rel_h=120.0 / 1.5, rate_tph=1.5, unload_h=0.5)
g2 = evaluate_case(specs(), stock_g2, CostParams(P_G2, S_RATE), c_g1, N, SEED)
show(g2)
c2 = g2["options"][0]
best_other = min(o["total"] for o in g2["options"][1:] if o["feasible"])
thr = g2["recommendation"]["threshold"]
check("Continue P(late) >= 50%", c2["p_late"] >= 0.50, f"{c2['p_late']:.1%}")
check("Continue P(stockout) <= 5%", c2["p_stockout"] <= 0.05, f"{c2['p_stockout']:.1%}")
check("Continue feasible", c2["feasible"], "no violated constraint")
check("No option beats Continue by more than the tie-break threshold", c2["total"] - best_other <= thr,
      f"Continue {c2['total']:,.0f}, best other {best_other:,.0f}, threshold {thr:,.0f}")
check("Recommendation NO JUSTIFIED INTERVENTION", g2["recommendation"]["code"] == "NO_JUSTIFIED_INTERVENTION",
      g2["recommendation"]["banner"])
print(f"    (recorded, not asserted) G2 stability: {g2['stability']['label']} {g2['stability']['holds']}/16")

print("\nG3 = G1 inputs, alpha = 1%, freight cap below Split freight")
cap = 20000.0
c_g3 = Constraints(alpha=0.01, max_freight_rs=cap, min_urgent_qty_t=A.min_urgent_qty_t,
                   tie_pct=A.tie_pct, tie_min_abs_rs=A.tie_min_abs_rs)
g3 = evaluate_case(specs(), stock_g1, CostParams(P_G1, S_RATE), c_g3, N, SEED)
show(g3)
o3 = {o["code"]: o for o in g3["options"]}
has = lambda o, k: any(v["constraint"] == k for v in o["violations"])  # noqa: E731
check("cap is below Split freight", cap < o3["SPLIT"]["freight"], f"cap {cap:,.0f} < {o3['SPLIT']['freight']:,.0f}")
check("Continue violates alpha", has(o3["CONTINUE"], "MAX_P_STOCKOUT"), "yes")
check("Reroute violates alpha", has(o3["REROUTE"], "MAX_P_STOCKOUT"), "yes")
check("Split violates the cost cap", has(o3["SPLIT"], "MAX_FREIGHT"), "yes")
check("NO FEASIBLE OPTION", g3["recommendation"]["code"] == "NO_FEASIBLE_OPTION", g3["recommendation"]["banner"])
check("nothing is labelled recommended", g3["recommendation"]["option_code"] is None,
      f"least-violating (information only): {g3['recommendation']['least_violating_code']}")

print("\nRESULT:", "ALL TARGETS COMPATIBLE - GO" if not FAILS else f"INFEASIBLE TARGETS: {FAILS}")
sys.exit(1 if FAILS else 0)
