"""Pydantic schemas: the single source of API truth (exported to contracts/openapi.json).

Customer responses use SEPARATE allow-list schemas (Customer*). They never contain
freight cost, penalty rate, stock-out rate, risk weights, option costs, other
customers' data or transporter performance. A test asserts key absence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from .assumptions import Assumptions


def _ser(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=None).isoformat() + "Z"


UTC = Annotated[datetime, PlainSerializer(_ser, return_type=str, when_used="json")]
Role = Literal["CUSTOMER", "COORDINATOR", "TRANSPORTER"]
State = Literal["PLANNED", "LOADING", "AT_PLANT_GATE", "IN_TRANSIT", "ARRIVED_AT_CUSTOMER_GATE", "DELIVERED"]
RiskCategory = Literal["LOW", "MEDIUM", "HIGH"]


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(Model):
    id: int
    username: str
    role: Role
    display_name: str
    customer_id: Optional[str] = None
    transporter_id: Optional[str] = None
    organisation: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut


# ---------- predictions ----------
class ReasonChip(BaseModel):
    key: str
    label: str
    hours: float


class P50Change(BaseModel):
    hours: float
    since: Optional[str] = None
    trigger: str
    trigger_event_id: Optional[str] = None


class Reasons(BaseModel):
    explains: str
    baseline_at: str
    mean_at: str
    chips: list[ReasonChip]
    notes: list[str]
    p50_change: Optional[P50Change] = None
    expected_late_hours: float
    expected_stockout_hours: Optional[float] = None
    stock_available: bool
    stock_depletion_at: Optional[str] = None
    telemetry_age_min: Optional[float] = None
    method: str


class PredictionOut(Model):
    id: int
    shipment_id: str
    created_sim_at: UTC
    n: int
    p10_at: UTC
    p50_at: UTC
    p90_at: UTC
    p_late: float
    p_stockout: Optional[float] = None
    risk_index: int
    risk_category: RiskCategory
    previous_p50_at: Optional[UTC] = None
    trigger: str
    trigger_event_id: Optional[str] = None
    reasons: Reasons
    data_confidence: Literal["FRESH", "AGING", "STALE"]
    state_version: int
    assumptions_version: int


class MilestoneOut(BaseModel):
    state: State
    label: str
    occurred_at: Optional[UTC] = None
    done: bool
    current: bool


# ---------- coordinator shipment views ----------
class ShipmentOut(BaseModel):
    id: str
    order_id: str
    customer_id: str
    customer_name: str
    product_code: str
    priority: str
    transporter_id: str
    transporter_name: str
    driver_name: Optional[str] = None
    vehicle_label: str
    route_id: str
    route_name: str
    destination_name: str
    active_alternative_route_id: Optional[str] = None
    alternative_route_name: Optional[str] = None
    parent_shipment_id: Optional[str] = None
    lot_type: str
    quantity_tonnes: float
    state: State
    state_label: str
    disposition: str
    state_version: int
    bucket: str
    planned_loading_at: UTC
    planned_arrival_at: UTC
    promised_at: UTC
    departed_at: Optional[UTC] = None
    arrived_at: Optional[UTC] = None
    delivered_at: Optional[UTC] = None
    last_telemetry_at: Optional[UTC] = None
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    last_progress_km: float
    total_km: float
    sla_penalty_per_late_hour: float
    prediction: Optional[PredictionOut] = None
    open_case_id: Optional[int] = None


class StockOut(BaseModel):
    available: bool
    note: str
    inventory_tonnes: Optional[float] = None
    measured_at: Optional[UTC] = None
    consumption_tph: Optional[float] = None
    unloading_hours: Optional[float] = None
    depletion_at: Optional[UTC] = None


class DisruptionOut(Model):
    id: str
    preset: Optional[str] = None
    label: str
    cause: Optional[str] = None
    kind: str
    route_id: Optional[str] = None
    segment_waypoint_id: Optional[str] = None
    shipment_id: Optional[str] = None
    start_at: UTC
    dur_min_h: float
    dur_mode_h: float
    dur_max_h: float
    multiplier: float
    status: str
    ended_at: Optional[UTC] = None


class ShipmentDetailOut(ShipmentOut):
    milestones: list[MilestoneOut]
    stock: StockOut
    disruptions: list[DisruptionOut]
    child_shipment_ids: list[str]


class EventOut(Model):
    id: int
    shipment_id: str
    type: str
    state: Optional[str] = None
    occurred_at: UTC
    note: str
    source: str


class OrderOut(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    product_code: str
    quantity_tonnes: float
    promised_at: UTC
    sla_penalty_per_late_hour: float
    priority: str
    revised_eta_communicated: Optional[UTC] = None
    revised_eta_communicated_at: Optional[UTC] = None
    shipment_ids: list[str]


# ---------- customer allow-list schemas ----------
class CustomerPoint(BaseModel):
    name: str
    lat: float
    lon: float


class CustomerPosition(BaseModel):
    lat: float
    lon: float
    reported_at: UTC
    note: str = "Last reported position (simulated)"


class CustomerEvent(BaseModel):
    at: UTC
    kind: str
    text: str


class CustomerHistoryItem(BaseModel):
    shipment_id: str
    order_id: str
    product_code: str
    quantity_tonnes: float
    promised_at: UTC
    arrived_at: UTC
    delivered_at: Optional[UTC] = None
    on_time: bool
    hours_vs_promise: float


class CustomerShipmentOut(BaseModel):
    id: str
    order_id: str
    product_code: str
    quantity_tonnes: float
    lot_type: str
    state: State
    state_label: str
    promised_at: UTC                                  # the original promise; never changes
    updated_expected_delivery: Optional[UTC] = None   # never called a "new commitment"
    eta_from: Optional[UTC] = None
    eta_to: Optional[UTC] = None
    risk_level: Optional[Literal["Low", "Medium", "High"]] = None
    data_confidence: Optional[str] = None
    route_name: str
    destination_name: str
    route_points: list[CustomerPoint]
    last_reported_position: Optional[CustomerPosition] = None
    milestones: list[MilestoneOut]
    arrived_at: Optional[UTC] = None
    delivered_at: Optional[UTC] = None
    action_note: Optional[str] = None
    stock_note: str
    progress_pct: int = 0
    delay_explanation: Optional[str] = None
    pod_status: str = "Not yet delivered"
    pod_recipient: Optional[str] = None
    timeline: list["CustomerEvent"] = []


class CustomerOrderOut(BaseModel):
    id: str
    product_code: str
    quantity_tonnes: float
    promised_at: UTC
    updated_expected_delivery: Optional[UTC] = None
    status: str
    shipments: list[CustomerShipmentOut]


class CustomerAlertOut(BaseModel):
    id: int
    shipment_id: Optional[str] = None
    order_id: Optional[str] = None
    severity: str
    title: str
    message: str
    suggested_action: str
    risk_level: Optional[str] = None
    eta_from: Optional[str] = None
    eta_to: Optional[str] = None
    promised_at: Optional[str] = None
    updated_expected_delivery: Optional[str] = None
    acknowledged: bool
    created_sim_at: UTC


# ---------- transporter ----------
class DriverShipmentOut(BaseModel):
    id: str
    order_id: str
    product_code: str
    quantity_tonnes: float
    lot_type: str
    vehicle_label: str
    route_name: str
    alternative_route_name: Optional[str] = None
    destination_name: str
    state: State
    state_label: str
    next_state: Optional[State] = None
    next_state_label: Optional[str] = None
    planned_loading_at: UTC
    promised_at: UTC
    milestones: list[MilestoneOut]
    pod_recipient: Optional[str] = None
    instruction: Optional[str] = None
    customer_name: str = ""
    priority: str = "NORMAL"
    progress_pct: int = 0
    progress_km: float = 0.0
    total_km: float = 0.0
    last_reported_at: Optional[UTC] = None
    can_report: bool = False
    active_report: Optional[str] = None
    pod_document_id: Optional[int] = None
    pod_document_name: Optional[str] = None
    pod_uploaded_at: Optional[UTC] = None


class DriverHistoryItem(BaseModel):
    shipment_id: str
    destination_name: str
    product_code: str
    quantity_tonnes: float
    promised_at: UTC
    arrived_at: UTC
    delivered_at: Optional[UTC] = None
    on_time: bool


class ReportIn(BaseModel):
    kind: Literal["BREAKDOWN", "ROAD_HAZARD"]
    note: Optional[str] = Field(None, max_length=200)


class ReportOut(BaseModel):
    disruption_id: str
    message: str
    shipment: "DriverShipmentOut"


class MilestoneIn(BaseModel):
    to_state: Literal["LOADING", "AT_PLANT_GATE", "IN_TRANSIT", "ARRIVED_AT_CUSTOMER_GATE"]
    occurred_at: Optional[datetime] = None


class PodIn(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=80)


# ---------- simulation ----------
class ClockOut(Model):
    sim_now: UTC
    speed: float
    paused: bool
    clock_version: int
    pause_on_alert: bool = True
    display_timezone: str = "Asia/Kolkata"


class AdvanceIn(BaseModel):
    minutes: int = Field(ge=5, le=720)


class AdvanceOut(BaseModel):
    clock: ClockOut
    predictions_recomputed: int


class DisruptionIn(BaseModel):
    preset: str = Field(min_length=1, max_length=40)
    shipment_id: Optional[str] = Field(None, max_length=40)
    start_offset_h: float = Field(0.0, ge=0, le=24)
    dur_min_h: Optional[float] = Field(None, ge=0, le=72)
    dur_mode_h: Optional[float] = Field(None, ge=0, le=72)
    dur_max_h: Optional[float] = Field(None, ge=0, le=72)
    multiplier: Optional[float] = Field(None, ge=1, le=5)


class PresetOut(BaseModel):
    code: str
    label: str
    cause: Optional[str] = None
    kind: str
    needs_shipment: bool
    requires_state: list[str]
    duration: list[float]
    multiplier: Optional[float] = None


# ---------- war room ----------
class LotMetrics(BaseModel):
    lot_type: str
    quantity_t: float
    p_late: float
    p50_at: str
    p90_at: str


class ScenarioMetrics(BaseModel):
    p50_at: str
    p90_at: str
    p_late: float
    p_stockout: Optional[float] = None
    exp_late_h: float
    exp_stockout_h: Optional[float] = None
    p_priority_ok: Optional[float] = None
    freight: float
    sla_cost: float
    stockout_cost: float
    total: float
    extra_km: float
    urgent_qty_t: Optional[float] = None
    lots: list[LotMetrics]


class ViolationOut(BaseModel):
    constraint: str
    value: float
    limit: float
    text: str


class ScenarioOut(BaseModel):
    id: int
    code: Literal["CONTINUE", "REROUTE", "SPLIT"]
    eligible: bool
    ineligible_reason: str
    feasible: bool
    metrics: Optional[ScenarioMetrics] = None
    violations: list[ViolationOut]
    summary: str


class RecommendationOut(BaseModel):
    code: str
    banner: str
    option_code: Optional[str] = None
    least_violating_code: Optional[str] = None
    saving_vs_continue: Optional[float] = None
    threshold: Optional[float] = None
    explanation: list[str] = []


class StabilityCase(BaseModel):
    freight: float
    sla_rate: float
    stockout_rate: float
    duration: float
    recommendation: str
    same: bool


class BreakEven(BaseModel):
    multipliers: dict[str, float]
    nearest: str
    nearest_multiplier: float


class StabilityOut(BaseModel):
    label: str
    holds: int
    total: int
    cases: list[StabilityCase]
    break_even: Optional[BreakEven] = None


class CaseOut(BaseModel):
    id: int
    shipment_id: str
    status: str
    recommendation: RecommendationOut
    stability: Optional[StabilityOut] = None
    constraints: dict[str, Any]
    context: dict[str, Any]
    shipment_state_version: int
    assumptions_version: int
    clock_version: int
    created_sim_at: UTC
    scenarios: list[ScenarioOut]
    selected_scenario_id: Optional[int] = None
    decided_sim_at: Optional[UTC] = None
    decided_by_name: Optional[str] = None
    is_override: bool
    override_reason: Optional[str] = None
    impact: Optional[dict[str, Any]] = None
    is_stale: bool
    stale_reason: Optional[str] = None


class ApproveIn(BaseModel):
    selected_scenario_id: int = Field(ge=1)
    override_reason: Optional[str] = Field(None, max_length=500)


class RejectIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


# ---------- alerts / audit ----------
class AlertOut(Model):
    id: int
    audience_role: str
    shipment_id: Optional[str] = None
    order_id: Optional[str] = None
    kind: str
    severity: str
    title: str
    message: str
    suggested_action: str
    data: dict[str, Any]
    acknowledged: bool
    escalation_level: int
    created_sim_at: UTC


class AuditOut(BaseModel):
    id: int
    actor: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    sim_time: UTC
    wall_time: UTC


# ---------- control tower / analytics ----------
class BucketCounts(BaseModel):
    LATE: int
    AT_RISK: int
    ON_TRACK: int
    ARRIVED_PENDING_POD: int
    DELIVERED: int
    active_total: int


class AnalyticsOverviewOut(BaseModel):
    active_orders: int = 0
    active_shipments: int = 0
    delayed_shipments: int = 0
    high_risk_shipments: int = 0
    avg_predicted_delay_hours: Optional[float] = None
    window_days: int
    orders_completed: int
    orders_on_time: int
    on_time_pct: Optional[float] = None
    average_delay_hours_late_orders: Optional[float] = None
    buckets: BucketCounts
    predicted_on_time_pct_active: Optional[float] = None
    warning_lead_time_hours: Optional[float] = None
    warning_lead_time_note: str
    definition: str


class ControlTowerOut(BaseModel):
    clock: ClockOut
    kpis: AnalyticsOverviewOut
    shipments: list[ShipmentOut]
    open_alerts: int


class MapPoint(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    is_decision_node: bool


class MapRoute(BaseModel):
    id: str
    name: str
    alternative_of: Optional[str] = None
    points: list[MapPoint]


class MapVehicle(BaseModel):
    shipment_id: str
    lat: float
    lon: float
    reported_at: Optional[UTC] = None
    age_min: Optional[float] = None
    data_confidence: str
    state: str
    risk_category: Optional[str] = None
    bucket: str
    route_id: str
    on_alternative: bool


class MapDisruption(BaseModel):
    id: str
    label: str
    kind: str
    lat1: float
    lon1: float
    lat2: float
    lon2: float


class MapDataOut(BaseModel):
    caption: str
    routes: list[MapRoute]
    vehicles: list[MapVehicle]
    disruptions: list[MapDisruption]


class DimensionRow(BaseModel):
    id: str
    name: str
    orders_completed: int
    orders_on_time: int
    on_time_pct: Optional[float] = None
    average_delay_hours_late_orders: Optional[float] = None
    attributed_delay_hours: float


class CauseRow(BaseModel):
    id: str
    name: str
    cause: str
    shipments_affected: int
    attributed_hours: float


class DelayCausesOut(BaseModel):
    by_route: list[CauseRow]
    by_transporter: list[CauseRow]
    totals: list[CauseRow]
    note: str


class BusinessImpactOut(BaseModel):
    label: str
    panel_a: dict[str, Any]
    panel_b: dict[str, Any]


class AssumptionsOut(BaseModel):
    values: Assumptions
    assumptions_version: int
    note: str = "Every value is a fictional, declared assumption - not Plant X or LYB policy."


class AssumptionsPutOut(AssumptionsOut):
    predictions_recomputed: int
    cases_superseded: int


class RefItem(BaseModel):
    id: str
    name: str


class OrderRoute(BaseModel):
    route_id: str
    route_name: str
    customer_name: str
    destination_name: str


class ReferenceDataOut(BaseModel):
    customers: list[RefItem]
    transporters: list[RefItem]
    routes: list[RefItem]
    states: list[RefItem]
    risk_categories: list[str]
    presets: list[PresetOut]
    demo_mode: bool
    products: list[str] = []
    order_routes: list["OrderRoute"] = []
    free_drivers: dict[str, int] = {}
    drivers: list["DriverRef"] = []


class HealthOut(BaseModel):
    status: str
    demo_mode: bool
    frontend_built_at: Optional[str] = None


class ResetOut(BaseModel):
    status: str
    active_shipments: int
    historical_shipments: int


# ---------- demo guide ----------
class DemoStep(BaseModel):
    tab: str
    do: str
    see: str
    link: str
    auto: bool


class DemoUseCase(BaseModel):
    code: str
    number: int
    title: str
    tagline: str
    proves: list[str]
    focus_shipment: str
    story: str
    tabs: list[str]
    steps: list[DemoStep]
    takeaway: str


class DemoGuideOut(BaseModel):
    demo_mode: bool
    password_hint: str
    use_cases: list[DemoUseCase]


class DemoSetupIn(BaseModel):
    mode: Literal["start", "jump"] = "start"


class DemoSetupOut(BaseModel):
    code: str
    mode: str
    steps_done_automatically: int
    message: str


# ---------- live operations ----------
class ActivityOut(BaseModel):
    id: str
    at: UTC
    kind: str
    severity: Literal["info", "ok", "warn", "alert"]
    title: str
    detail: str = ""
    shipment_id: Optional[str] = None
    source: str


class SyncOut(BaseModel):
    stamp: str
    sim_now: UTC
    paused: bool
    speed: float


class ClockControlIn(BaseModel):
    paused: Optional[bool] = None
    speed: Optional[float] = Field(None, ge=1, le=60)
    pause_on_alert: Optional[bool] = None


class OrderCreateIn(BaseModel):
    route_id: str = Field(min_length=1, max_length=20)
    transporter_id: str = Field(min_length=1, max_length=20)
    product_code: str = Field(min_length=1, max_length=20)
    quantity_tonnes: float = Field(gt=0, le=40)
    priority: Literal["NORMAL", "HIGH"] = "NORMAL"
    sla_penalty_per_late_hour: Optional[float] = Field(None, ge=0, le=100000)
    loading_in_h: float = Field(1.0, ge=0, le=24)
    promised_in_h: Optional[float] = Field(None, ge=1, le=240)


class OrderCreatedOut(BaseModel):
    order_id: str
    shipment_id: str
    customer_name: str
    transporter_name: str
    driver_name: str
    driver_username: str
    vehicle_label: str
    promised_at: UTC
    planned_loading_at: UTC
    message: str


class ControlOut(BaseModel):
    clock: ClockOut
    runner_error: Optional[str] = None


CustomerShipmentOut.model_rebuild()
ReportOut.model_rebuild()



# ---------- gate slot booking ----------
BookingStatus = Literal["BOOKED", "CHECKED_IN", "COMPLETED", "CANCELLED", "MISSED"]


class BookingOut(BaseModel):
    id: int
    shipment_id: str
    order_id: str
    product_code: str
    quantity_tonnes: float
    customer_name: str
    transporter_id: str
    transporter_name: str
    driver_id: Optional[int] = None
    driver_name: Optional[str] = None
    driver_username: Optional[str] = None
    vehicle_label: str
    slot_id: int
    slot_start: UTC
    slot_end: UTC
    status: BookingStatus
    created_sim_at: UTC
    checked_in_at: Optional[UTC] = None
    completed_at: Optional[UTC] = None
    cancelled_at: Optional[UTC] = None
    cancel_reason: Optional[str] = None
    rescheduled_from: Optional[UTC] = None
    shipment_state: str
    check_in_opens_at: UTC


class SlotOut(BaseModel):
    id: int
    slot_start: UTC
    slot_end: UTC
    capacity: int
    booked: int
    available: int
    state: Literal["OPEN", "FULL", "OVERBOOKED", "UNAVAILABLE", "PAST"]
    note: str
    bookings: list[BookingOut]


class GateOverviewOut(BaseModel):
    sim_now: UTC
    default_capacity: int
    check_in_early_minutes: int
    gate_name: str
    slots: list[SlotOut]


class GateSummaryOut(BaseModel):
    day_label: str
    capacity: int
    booked: int
    full_slots: int
    unavailable_slots: int
    upcoming: list[BookingOut]


class BookIn(BaseModel):
    shipment_id: str = Field(min_length=1, max_length=40)
    slot_id: int = Field(ge=1)
    transporter_id: Optional[str] = Field(None, max_length=20)
    driver_user_id: Optional[int] = Field(None, ge=1)


class RescheduleIn(BaseModel):
    slot_id: int = Field(ge=1)


class CancelIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=200)


class SlotUpdateIn(BaseModel):
    capacity: Optional[int] = Field(None, ge=0, le=50)
    closed: Optional[bool] = None
    note: Optional[str] = Field(None, max_length=120)


class DriverBookingOut(BaseModel):
    id: int
    shipment_id: str
    order_id: str
    product_code: str
    quantity_tonnes: float
    vehicle_label: str
    slot_start: UTC
    slot_end: UTC
    status: BookingStatus
    gate_name: str
    gate_instructions: str
    can_check_in: bool
    check_in_hint: Optional[str] = None
    check_in_opens_at: UTC
    checked_in_at: Optional[UTC] = None
    completed_at: Optional[UTC] = None
    cancel_reason: Optional[str] = None


class DriverRef(BaseModel):
    id: int
    name: str
    username: str
    transporter_id: str


# ---------- documents (invoice and proof of delivery) ----------
class DocumentOut(BaseModel):
    id: int
    kind: Literal["INVOICE", "POD"]
    order_id: str
    shipment_id: Optional[str] = None
    version: int
    is_current: bool
    status: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    invoice_number: Optional[str] = None
    recipient_name: Optional[str] = None
    uploaded_by_name: str
    uploaded_by_role: str
    uploaded_sim_at: UTC
    delivered_sim_at: Optional[UTC] = None
    replace_reason: Optional[str] = None
    verified_by_name: Optional[str] = None
    verified_sim_at: Optional[UTC] = None


class ShipmentDocsOut(BaseModel):
    shipment_id: str
    state: str
    state_label: str
    lot_type: str
    quantity_tonnes: float
    pod_status: Literal["NOT_DELIVERED", "AWAITING_POD", "NO_DOCUMENT", "UPLOADED", "VERIFIED"]
    recipient_name: Optional[str] = None
    delivered_at: Optional[UTC] = None
    documents: list[DocumentOut]


class OrderDocumentsOut(BaseModel):
    order_id: str
    customer_name: str
    invoices: list[DocumentOut]
    shipments: list[ShipmentDocsOut]


class DocumentsOverviewRow(BaseModel):
    order_id: str
    customer_name: str
    product_code: str
    quantity_tonnes: float
    shipment_ids: list[str]
    shipment_states: list[str]
    invoice: Optional[DocumentOut] = None
    pods_expected: int
    pods_delivered: int
    pods_uploaded: int
    pods_verified: int


class CustomerDocumentOut(BaseModel):
    id: int
    kind: Literal["INVOICE", "POD"]
    order_id: str
    shipment_id: Optional[str] = None
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: UTC
    status: str
    invoice_number: Optional[str] = None
    recipient_name: Optional[str] = None
    delivered_at: Optional[UTC] = None


class UploadResultOut(BaseModel):
    document: DocumentOut
    message: str


class PodUploadOut(BaseModel):
    document: DocumentOut
    shipment: "DriverShipmentOut"
    message: str


# ---------- "Where is my order?" chatbot ----------
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    order_id: Optional[str] = Field(None, max_length=40)


class ChatFact(BaseModel):
    label: str
    value: str


class ChatLink(BaseModel):
    kind: Literal["order", "document", "tab"]
    label: str
    order_id: Optional[str] = None
    document_id: Optional[int] = None
    tab: Optional[str] = None


class ChatPosition(BaseModel):
    lat: float
    lon: float
    reported_at: UTC
    near: str
    progress_pct: int


class ChatReplyOut(BaseModel):
    text: str
    intent: str
    order_id: Optional[str] = None
    facts: list[ChatFact] = []
    links: list[ChatLink] = []
    suggestions: list[str] = []
    position: Optional[ChatPosition] = None
    as_of: UTC


PodUploadOut.model_rebuild()

ReferenceDataOut.model_rebuild()
