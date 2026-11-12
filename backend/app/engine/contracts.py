"""Typed engine inputs and outputs (frozen contract).

Units: hours for durations, km for distance, tonnes for quantity, t/h for
consumption, Rs for currency. All times are RELATIVE HOURS from t_now = 0;
the mapping layer converts timestamps. The engine imports only numpy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class Tri:
    """Triangular distribution parameters, in hours."""
    low: float
    mode: float
    high: float

    def __post_init__(self):
        if not (self.low <= self.mode <= self.high):
            raise ValueError(f"Tri requires low <= mode <= high, got {self}")
        if self.low < 0:
            raise ValueError("Tri durations must be >= 0")

    def scaled(self, k: float) -> "Tri":
        return Tri(self.low * k, self.mode * k, self.high * k)

    @property
    def mean(self) -> float:
        return (self.low + self.mode + self.high) / 3.0


@dataclass(frozen=True)
class SegmentInput:
    key: str            # stable id, also the name of its variate column
    km: float           # remaining km on this segment
    speed_kmh: float
    already_inside: bool = False  # vehicle is already on it: closures do not apply

    @property
    def base_hours(self) -> float:
        return self.km / self.speed_kmh


@dataclass(frozen=True)
class HandlingStage:
    name: str
    ref_hours: float     # deterministic reference duration of the whole stage
    dist: Tri            # sampled duration of the whole stage
    elapsed_h: float = 0.0  # time already spent in this stage


@dataclass(frozen=True)
class ClosureInput:
    key: str
    segment_key: str
    start_rel_h: float   # <= 0 means already active
    duration: Tri


@dataclass(frozen=True)
class SlowdownInput:
    key: str
    segment_key: str
    start_rel_h: float
    duration: Tri
    multiplier: float    # >= 1


@dataclass(frozen=True)
class RepairInput:
    key: str
    elapsed_h: float
    duration: Tri


@dataclass(frozen=True)
class EngineInputs:
    segments: tuple[SegmentInput, ...]
    promised_rel_h: float
    handling_stages: tuple[HandlingStage, ...] = ()
    gate_queue: Optional[Tri] = None       # only while still queued
    planned_wait_h: float = 0.0            # planned wait before handling (part of baseline)
    dispatch_delay_h: float = 0.0          # LATE_DISPATCH offset or second-vehicle lead time
    closures: tuple[ClosureInput, ...] = ()
    slowdowns: tuple[SlowdownInput, ...] = ()
    repair: Optional[RepairInput] = None
    sigma_route: float = 0.10
    sigma_segment: float = 0.05
    sigma_scale: float = 1.0               # transporter factor x stale-data factor
    lot_key: str = ""                      # prefix for lot-specific variate columns
    residual_floor_h: float = 0.5


COMPONENT_KEYS = (
    "handling_deviation", "gate_queue", "dispatch_delay", "slowdown",
    "closure_wait", "repair_wait", "variability",
)


@dataclass
class EngineResult:
    samples: np.ndarray                    # arrival time T_i, relative hours
    n: int
    seed: int
    p10: float
    p50: float
    p90: float
    mean: float
    p_late: float
    expected_late_hours: float
    baseline_h: float
    components: dict = field(default_factory=dict)   # mean contributions, hours


@dataclass(frozen=True)
class StockParams:
    depletion_rel_h: float   # S: when current stock runs out, relative hours
    rate_tph: float          # r
    unload_h: float          # u


@dataclass(frozen=True)
class LotSpec:
    lot_type: str            # SINGLE | URGENT | REMAINDER
    quantity_t: float
    inputs: EngineInputs


@dataclass(frozen=True)
class OptionSpec:
    code: str                # CONTINUE | REROUTE | SPLIT
    eligible: bool
    ineligible_reason: str = ""
    lots: tuple[LotSpec, ...] = ()
    freight_rs: float = 0.0  # incremental freight at freight scale 1.0
    extra_km: float = 0.0


@dataclass(frozen=True)
class CostParams:
    sla_per_late_hour: float          # p
    stockout_per_hour: float          # s (incremental, beyond p)
    freight_scale: float = 1.0


@dataclass(frozen=True)
class Constraints:
    alpha: float = 0.10                       # max P(stock-out)
    max_freight_rs: Optional[float] = None    # max incremental freight
    min_urgent_qty_t: float = 0.0
    beta: Optional[float] = None              # max P(late), off by default
    tie_pct: float = 0.02
    tie_min_abs_rs: float = 2000.0
