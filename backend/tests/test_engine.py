"""Engine unit and metamorphic tests (spec section 7). Pure: no database, no API."""
import dataclasses
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from app.engine.contracts import (ClosureInput, Constraints, CostParams, EngineInputs, HandlingStage, LotSpec,
                                  OptionSpec, SegmentInput, SlowdownInput, StockParams, Tri)
from app.engine.eta import sample_end_rel, simulate_arrival, tri_cdf, tri_inv
from app.engine.risk import risk_category, risk_index
from app.engine.stock import stockout_hours
from app.engine.warroom import apply_costs, evaluate_case, raw_metrics

N, SEED = 500, 12345
SEGS = (SegmentInput("a", 90, 45), SegmentInput("b", 90, 45), SegmentInput("c", 90, 45))


def make(closure_tri=None, promised=9.0, **kw):
    closures = (ClosureInput("c1", "b", 0.0, closure_tri),) if closure_tri else ()
    return EngineInputs(segments=SEGS, promised_rel_h=promised, gate_queue=Tri(0.2, 0.5, 1.0), closures=closures, **kw)


def test_percentiles_are_ordered():
    r = simulate_arrival(make(Tri(3, 5, 8)), N, SEED)
    assert r.p10 <= r.p50 <= r.p90


def test_longer_disruption_never_lowers_p_late():
    prev = -1.0
    for k in (0.5, 1.0, 1.5, 2.0, 3.0):
        p = simulate_arrival(make(Tri(3, 5, 8).scaled(k), promised=8.0), N, SEED).p_late
        assert p >= prev - 1e-12
        prev = p


def test_earlier_deadline_never_lowers_p_late():
    prev = -1.0
    for d in (12.0, 10.0, 9.0, 8.0, 7.0, 6.0):
        p = simulate_arrival(make(Tri(3, 5, 8), promised=d), N, SEED).p_late
        assert p >= prev - 1e-12
        prev = p


def test_reason_chips_sum_to_mean_minus_baseline():
    inp = make(Tri(3, 5, 8), handling_stages=(HandlingStage("loading", 1.0, Tri(0.8, 1.0, 1.5), 0.3),),
               slowdowns=(SlowdownInput("s1", "c", 0.0, Tri(6, 8, 10), 1.5),), dispatch_delay_h=0.4)
    r = simulate_arrival(inp, N, SEED)
    assert sum(r.components.values()) == pytest.approx(r.mean - r.baseline_h, abs=1e-9)
    assert r.components["closure_wait"] > 0 and r.components["slowdown"] > 0


def test_residual_is_zero_in_deterministic_no_disruption_baseline():
    inp = EngineInputs(segments=SEGS, promised_rel_h=9.0, sigma_route=0.0, sigma_segment=0.0)
    r = simulate_arrival(inp, N, SEED)
    assert r.components["variability"] == pytest.approx(0.0, abs=1e-9)
    assert r.p10 == pytest.approx(6.0) and r.p90 == pytest.approx(6.0)     # 270 km / 45 km/h


def test_identical_inputs_and_seed_give_identical_results_twice():
    a = simulate_arrival(make(Tri(3, 5, 8)), N, SEED)
    b = simulate_arrival(make(Tri(3, 5, 8)), N, SEED)
    assert [round(x, 6) for x in (a.p10, a.p50, a.p90, a.p_late)] == [round(x, 6) for x in (b.p10, b.p50, b.p90, b.p_late)]


def test_identical_results_across_two_processes():
    code = ("from app.engine.contracts import *; from app.engine.eta import simulate_arrival;"
            "s=(SegmentInput('a',90,45),SegmentInput('b',90,45),SegmentInput('c',90,45));"
            "r=simulate_arrival(EngineInputs(segments=s,promised_rel_h=9.0,gate_queue=Tri(0.2,0.5,1.0),"
            "closures=(ClosureInput('c1','b',0.0,Tri(3,5,8)),)),500,12345);"
            "print(round(r.p10,6),round(r.p50,6),round(r.p90,6),round(r.p_late,6))")
    cwd = Path(__file__).resolve().parents[1]
    outs = {subprocess.run([sys.executable, "-c", code], cwd=cwd, capture_output=True, text=True, check=True).stdout
            for _ in range(2)}
    assert len(outs) == 1
    here = simulate_arrival(make(Tri(3, 5, 8)), N, SEED)
    assert outs.pop().split() == [str(round(x, 6)) for x in (here.p10, here.p50, here.p90, here.p_late)]


def test_sanity_promise_beyond_p90_means_low_p_late():
    r = simulate_arrival(make(), N, SEED)
    assert simulate_arrival(make(promised=r.p90), N, SEED).p_late <= 0.10 + 1e-9
    assert simulate_arrival(make(promised=r.p50 - 0.01), N, SEED).p_late > 0.50


def test_stale_scale_widens_uncertainty_without_moving_the_baseline():
    fresh = simulate_arrival(make(), N, SEED)
    stale = simulate_arrival(make(sigma_scale=3.0), N, SEED)
    assert (stale.p90 - stale.p10) > (fresh.p90 - fresh.p10)
    assert stale.baseline_h == pytest.approx(fresh.baseline_h)


def test_active_closure_residual_never_implies_it_already_ended():
    u = np.linspace(0.001, 0.999, 200)
    tri = Tri(2, 4, 6)
    for elapsed in (0.0, 1.0, 3.0, 5.5):
        assert (sample_end_rel(u, -elapsed, tri, 0.5) >= -1e-9).all()
    overdue = sample_end_rel(u, -7.0, tri, 0.5)                 # F(e) >= 0.999: short floor residual
    assert (overdue >= 0).all() and (overdue <= 0.5).all()
    future = sample_end_rel(u, 2.0, tri, 0.5)                   # not started: unconditional
    assert (future >= 4.0 - 1e-9).all() and (future <= 8.0 + 1e-9).all()


def test_triangular_cdf_and_inverse_round_trip():
    tri = Tri(1, 2, 5)
    u = np.linspace(0.01, 0.99, 50)
    assert np.allclose(tri_cdf(tri_inv(u, tri), tri), u, atol=1e-9)


def test_overlapping_closures_are_not_double_counted():
    one = make(Tri(3, 5, 8))
    two = dataclasses.replace(one, closures=one.closures + (ClosureInput("c1", "b", 0.0, Tri(3, 5, 8)),))
    a, b = simulate_arrival(one, N, SEED), simulate_arrival(two, N, SEED)
    assert b.components["closure_wait"] == pytest.approx(a.components["closure_wait"])


def test_closure_does_not_affect_a_vehicle_already_inside_the_segment():
    segs = (SegmentInput("b", 40, 45, already_inside=True), SegmentInput("c", 90, 45))
    inp = EngineInputs(segments=segs, promised_rel_h=5.0, closures=(ClosureInput("c1", "b", 0.0, Tri(3, 5, 8)),))
    assert simulate_arrival(inp, N, SEED).components["closure_wait"] == 0.0


def test_transporter_factor_scales_spread_not_mean():
    a = simulate_arrival(make(), 4000, SEED)
    b = simulate_arrival(make(sigma_scale=1.3), 4000, SEED)
    assert b.mean == pytest.approx(a.mean, abs=0.08)
    assert (b.p90 - b.p10) > (a.p90 - a.p10)


# ---------- risk ----------
def test_risk_index_and_floors():
    assert risk_index(0.5, 0.5, 0.6, 0.4) == 50
    assert risk_index(0.4, None, 0.6, 0.4) == 40                # no stock data: w_late = 1
    assert risk_category(10, 0.10, 0.0) == "LOW"
    assert risk_category(15, 0.25, 0.0) == "MEDIUM"             # floor: P(late) >= 25%
    assert risk_category(30, 0.50, 0.0) == "HIGH"               # floor: P(late) >= 50%
    assert risk_category(12, 0.0, 0.30) == "HIGH"               # floor: P(stock-out) >= 30%
    assert risk_category(65, 0.0, 0.0) == "HIGH"                # band


# ---------- war room ----------
def specs(promised=9.0):
    base = make(Tri(6, 8, 10), promised=promised)
    alt = EngineInputs(segments=(SegmentInput("a", 90, 45), SegmentInput("x", 130, 45), SegmentInput("c", 90, 45)),
                       promised_rel_h=promised, gate_queue=Tri(0.2, 0.5, 1.0))
    return [OptionSpec("CONTINUE", True, lots=(LotSpec("SINGLE", 24, base),)),
            OptionSpec("REROUTE", True, lots=(LotSpec("SINGLE", 24, alt),), freight_rs=7000, extra_km=40),
            OptionSpec("SPLIT", False, "not before departure")]


STOCK = StockParams(depletion_rel_h=10.5, rate_tph=2.0, unload_h=0.5)


def test_doubling_p_changes_total_only_through_the_sla_term():
    raw = raw_metrics(specs()[0], STOCK, N, SEED)
    a, b = apply_costs(raw, CostParams(1000, 500)), apply_costs(raw, CostParams(2000, 500))
    assert b["freight"] == a["freight"] and b["stockout_cost"] == a["stockout_cost"]
    assert b["sla_cost"] == pytest.approx(2 * a["sla_cost"])
    assert b["total"] - a["total"] == pytest.approx(a["sla_cost"])


def test_infeasible_option_is_never_recommended():
    case = evaluate_case(specs(), STOCK, CostParams(20000, 60000), Constraints(alpha=0.0, max_freight_rs=1.0), N, SEED)
    rec = case["recommendation"]
    assert rec["code"] == "NO_FEASIBLE_OPTION" and rec["option_code"] is None
    assert rec["least_violating_code"] in ("CONTINUE", "REROUTE")
    assert case["stability"]["label"] == "NO ROBUST RECOMMENDATION"
    for c in (Constraints(alpha=0.10), Constraints(alpha=0.5), Constraints(alpha=0.10, max_freight_rs=100.0)):
        case = evaluate_case(specs(), STOCK, CostParams(20000, 60000), c, N, SEED)
        code = case["recommendation"]["option_code"]
        if code:
            assert next(o for o in case["options"] if o["code"] == code)["feasible"]


def test_ineligible_option_stays_visible_with_reason():
    case = evaluate_case(specs(), STOCK, CostParams(20000, 60000), Constraints(), N, SEED)
    split = case["options"][2]
    assert split["eligible"] is False and split["ineligible_reason"] and split["feasible"] is False


def test_zero_baseline_means_no_justified_intervention():
    case = evaluate_case(specs(promised=40.0), None, CostParams(20000, 60000), Constraints(), N, SEED)
    assert case["options"][0]["total"] == 0.0
    assert case["recommendation"]["code"] == "NO_JUSTIFIED_INTERVENTION"


def test_stability_has_16_cases_and_consistent_label():
    case = evaluate_case(specs(), STOCK, CostParams(20000, 60000), Constraints(), N, SEED)
    st = case["stability"]
    assert st["total"] == 16 and len(st["cases"]) == 16
    assert st["holds"] == sum(c["same"] for c in st["cases"])
    expected = "STABLE" if st["holds"] == 16 else "SENSITIVE" if st["holds"] >= 8 else "NO ROBUST RECOMMENDATION"
    assert st["label"] == expected


def test_split_sla_is_quantity_weighted_and_stock_uses_sequential_model():
    urgent = EngineInputs(segments=SEGS, promised_rel_h=7.0, lot_key="lot:URGENT|", sigma_route=0, sigma_segment=0)
    rem = EngineInputs(segments=SEGS, promised_rel_h=7.0, lot_key="lot:REMAINDER|", sigma_route=0, sigma_segment=0,
                       dispatch_delay_h=3.0)
    sp = OptionSpec("SPLIT", True, lots=(LotSpec("URGENT", 8, urgent), LotSpec("REMAINDER", 16, rem)), freight_rs=100)
    raw = raw_metrics(sp, StockParams(6.2, 2.0, 0.5), N, SEED)
    # urgent arrives 6.0 (on time); remainder 9.0 (2 h late); weighted late = 16/24 * 2
    assert raw["exp_late_h"] == pytest.approx(16 / 24 * 2.0)
    # A_u = 6.5 > S = 6.2 -> 0.3 h stock-out; cover_end = 6.5 + 8/2 = 10.5; A_r = 9.5 -> none
    assert raw["exp_stockout_h"] == pytest.approx(0.3)
    assert raw["p_late"] == 1.0                                   # order is late if any lot is late


def test_common_random_numbers_pair_the_options():
    """Reroute and Continue share shipment-level factors: their samples are strongly correlated."""
    case_specs = specs()
    cont = simulate_arrival(dataclasses.replace(case_specs[0].lots[0].inputs, closures=()), N, SEED).samples
    rer = simulate_arrival(case_specs[1].lots[0].inputs, N, SEED).samples
    assert np.corrcoef(cont, rer)[0, 1] > 0.9


def test_stockout_helper_matches_single_lot_formula():
    t = np.array([5.0, 9.0, 12.0])
    out = stockout_hours([(t, 24.0)], StockParams(10.0, 2.0, 0.5))
    assert out.tolist() == [0.0, 0.0, 2.5]                        # max(0, A - S)
