"""Editable business and modelling assumptions (D4).

Every value is a declared, fictional assumption - not LYB or Plant X policy.
Stored as one JSON row with an assumptions_version; validated by Pydantic.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Assumptions(BaseModel):
    # --- engine ---
    n_samples: int = Field(500, ge=100, le=5000)
    sigma_route: float = Field(0.10, ge=0.0, le=0.6)
    sigma_segment: float = Field(0.05, ge=0.0, le=0.6)
    loading_ref_h: float = Field(1.0, gt=0, le=12)
    loading_min_h: float = Field(0.8, ge=0, le=12)
    loading_mode_h: float = Field(1.0, ge=0, le=12)
    loading_max_h: float = Field(1.5, ge=0, le=24)
    gate_min_h: float = Field(0.2, ge=0, le=12)
    gate_mode_h: float = Field(0.5, ge=0, le=12)
    gate_max_h: float = Field(1.0, ge=0, le=24)
    residual_floor_h: float = Field(0.5, gt=0, le=6)
    fresh_minutes: float = Field(15, gt=0, le=600)
    stale_minutes: float = Field(45, gt=0, le=1440)
    # --- risk index ---
    w_late: float = Field(0.6, ge=0, le=1)
    w_stock: float = Field(0.4, ge=0, le=1)
    band_medium_from: int = Field(30, ge=1, le=99)
    band_high_from: int = Field(60, ge=2, le=100)
    alert_expected_wait_h: float = Field(2.0, ge=0, le=48)
    grace_hours: float = Field(0.0, ge=0, le=24)
    # --- plant gate ---
    gate_slot_capacity: int = Field(3, ge=1, le=50, description="vehicles per hourly gate slot (new slots)")
    # --- war room constraints ---
    alpha: float = Field(0.10, ge=0, le=1, description="max P(stock-out)")
    max_incremental_freight_rs: Optional[float] = Field(None, ge=0)
    min_urgent_qty_t: float = Field(6.0, ge=0, le=100)
    beta: Optional[float] = Field(None, ge=0, le=1, description="max P(late); off when null")
    # --- war room costs (fictional Rs) ---
    stockout_cost_per_hour_rs: float = Field(60000, ge=0, le=1e8)
    reroute_fixed_rs: float = Field(5000, ge=0, le=1e7)
    second_vehicle_fixed_rs: float = Field(18000, ge=0, le=1e7)
    second_vehicle_lead_h: float = Field(1.5, ge=0, le=48)
    split_cover_hours: float = Field(4.0, gt=0, le=240)
    tie_pct: float = Field(0.02, ge=0, le=1)
    tie_min_abs_rs: float = Field(2000, ge=0, le=1e7)
    # --- business impact panel B (illustrative) ---
    annual_shipments: float = Field(6000, gt=0, le=1e7)
    delay_rate: float = Field(0.18, gt=0, le=1)
    mitigable_share: float = Field(0.40, gt=0, le=1)
    success_rate: float = Field(0.70, gt=0, le=1)
    avoidable_hours: float = Field(3.0, gt=0, le=240)
    cost_per_late_hour_rs: float = Field(15000, ge=0, le=1e8)
    avg_intervention_cost_rs: float = Field(12000, ge=0, le=1e8)

    @model_validator(mode="after")
    def _check(self):
        if abs(self.w_late + self.w_stock - 1.0) > 1e-6:
            raise ValueError("w_late + w_stock must equal 1")
        if not (self.loading_min_h <= self.loading_mode_h <= self.loading_max_h):
            raise ValueError("loading triangular must satisfy min <= mode <= max")
        if not (self.gate_min_h <= self.gate_mode_h <= self.gate_max_h):
            raise ValueError("gate queue triangular must satisfy min <= mode <= max")
        if self.band_medium_from >= self.band_high_from:
            raise ValueError("band_medium_from must be below band_high_from")
        if self.fresh_minutes >= self.stale_minutes:
            raise ValueError("fresh_minutes must be below stale_minutes")
        return self


# Disruption presets: parameterised events with validated bounds (spec 4.5).
PRESETS = {
    "FLOOD_R1": {"label": "Flooding - Tapi River Bridge (Waluj to Pithampur road)", "cause": "FLOODING", "kind": "CLOSURE",
                 "route_id": "R1", "segment_waypoint_id": "R1-W2", "duration": (7.0, 9.0, 12.0)},
    "FLOOD_R2": {"label": "Flooding - Buldhana market town (Waluj to Amravati road)", "cause": "FLOODING", "kind": "CLOSURE",
                 "route_id": "R2", "segment_waypoint_id": "R2-W2", "duration": (4.0, 6.0, 9.0)},
    "CONGESTION_R3": {"label": "Route congestion - Supa Toll Plaza (Waluj to Satara road)", "cause": "ROUTE_CONGESTION",
                      "kind": "SLOWDOWN", "route_id": "R3", "segment_waypoint_id": "R3-W2",
                      "duration": (3.0, 5.0, 8.0), "multiplier": 1.6},
    "GATE_CONGESTION": {"label": "Plant gate congestion", "cause": "GATE_CONGESTION", "kind": "GATE_QUEUE_SHIFT",
                        "duration": (2.0, 3.0, 5.0), "multiplier": 2.5},
    "SLOW_LOADING": {"label": "Slow loading at Plant X", "cause": "SLOW_LOADING", "kind": "HANDLING_SHIFT",
                     "duration": (2.0, 4.0, 6.0), "multiplier": 1.8},
}
