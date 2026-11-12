"""Database tables (spec 4.14). Timestamps are naive UTC. No Alembic: create_all + seed."""
from sqlalchemy import (JSON, Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint, func, text)

from .db import Base

STATES = ("PLANNED", "LOADING", "AT_PLANT_GATE", "IN_TRANSIT", "ARRIVED_AT_CUSTOMER_GATE", "DELIVERED")
ROLES = ("CUSTOMER", "COORDINATOR", "TRANSPORTER")
CAUSES = ("FLOODING", "BREAKDOWN", "GATE_CONGESTION", "SLOW_LOADING", "LATE_DISPATCH", "ROUTE_CONGESTION")
KINDS = ("CLOSURE", "SLOWDOWN", "VEHICLE_STOPPAGE", "GATE_QUEUE_SHIFT", "HANDLING_SHIFT",
         "DEPARTURE_OFFSET", "TELEMETRY_OUTAGE")


def _in(col, values):
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Stamp:
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Customer(Base, Stamp):
    __tablename__ = "customers"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class Transporter(Base, Stamp):
    __tablename__ = "transporters"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    sigma_factor = Column(Float, nullable=False, default=1.0)   # scales uncertainty only, never the mean


class User(Base, Stamp):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"))
    transporter_id = Column(String, ForeignKey("transporters.id"))
    is_active = Column(Boolean, nullable=False, default=True)
    __table_args__ = (CheckConstraint(_in("role", ROLES)),)


class Route(Base, Stamp):
    __tablename__ = "routes"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    destination_name = Column(String, nullable=False)
    cost_per_km = Column(Float, nullable=False)
    road_circuity_factor = Column(Float, nullable=False, default=1.2)
    # an alternative route names its primary, entry decision node and rejoin point explicitly
    alternative_of_route_id = Column(String, ForeignKey("routes.id"))
    alternative_entry_decision_node_id = Column(String)
    alternative_rejoin_waypoint_id = Column(String)


class RouteWaypoint(Base, Stamp):
    __tablename__ = "route_waypoints"
    id = Column(String, primary_key=True)
    route_id = Column(String, ForeignKey("routes.id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    is_decision_node = Column(Boolean, nullable=False, default=False)
    speed_kmh_to_next = Column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("route_id", "sequence"), CheckConstraint("speed_kmh_to_next > 0"))


class Order(Base, Stamp):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    product_code = Column(String, nullable=False)
    quantity_tonnes = Column(Float, nullable=False)
    promised_at = Column(DateTime, nullable=False)          # immutable deadline at the customer gate
    sla_penalty_per_late_hour = Column(Float, nullable=False)
    priority = Column(String, nullable=False, default="NORMAL")
    revised_eta_communicated = Column(DateTime)             # communication record only, never a KPI input
    revised_eta_communicated_at = Column(DateTime)
    __table_args__ = (CheckConstraint("quantity_tonnes > 0"), CheckConstraint("sla_penalty_per_late_hour >= 0"),
                      CheckConstraint("priority IN ('NORMAL', 'HIGH')"))


class Shipment(Base, Stamp):
    __tablename__ = "shipments"
    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    transporter_id = Column(String, ForeignKey("transporters.id"), nullable=False, index=True)
    driver_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    vehicle_label = Column(String, nullable=False)
    route_id = Column(String, ForeignKey("routes.id"), nullable=False, index=True)
    active_alternative_route_id = Column(String, ForeignKey("routes.id"))
    parent_shipment_id = Column(String, ForeignKey("shipments.id"))
    lot_type = Column(String, nullable=False, default="SINGLE")
    quantity_tonnes = Column(Float, nullable=False)
    planned_loading_at = Column(DateTime, nullable=False)
    planned_arrival_at = Column(DateTime, nullable=False)
    state = Column(String, nullable=False, default="PLANNED", index=True)
    state_entered_at = Column(DateTime, nullable=False)
    disposition = Column(String, nullable=False, default="ACTIVE")
    state_version = Column(Integer, nullable=False, default=1)
    last_telemetry_at = Column(DateTime)
    last_lat = Column(Float)
    last_lon = Column(Float)
    last_progress_km = Column(Float, nullable=False, default=0.0)
    departed_at = Column(DateTime)
    arrived_at = Column(DateTime)
    delivered_at = Column(DateTime)
    pod_recipient = Column(String)
    is_historical = Column(Boolean, nullable=False, default=False, index=True)
    __table_args__ = (CheckConstraint(_in("state", STATES)),
                      CheckConstraint("disposition IN ('ACTIVE', 'SPLIT_PARENT')"),
                      CheckConstraint("lot_type IN ('SINGLE', 'URGENT', 'REMAINDER')"),
                      CheckConstraint("quantity_tonnes > 0"))


class ShipmentEvent(Base, Stamp):
    __tablename__ = "shipment_events"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(String, ForeignKey("shipments.id"), nullable=False, index=True)
    type = Column(String, nullable=False)        # MILESTONE | DISRUPTION_START | DISRUPTION_END | REROUTED | SPLIT | POD
    state = Column(String)
    occurred_at = Column(DateTime, nullable=False)
    note = Column(Text, nullable=False, default="")
    actor_user_id = Column(Integer, ForeignKey("users.id"))
    source = Column(String, nullable=False, default="SYSTEM")   # DRIVER | SIMULATED | COORDINATOR | SYSTEM


class Disruption(Base, Stamp):
    __tablename__ = "disruptions"
    id = Column(String, primary_key=True)
    preset = Column(String)
    label = Column(String, nullable=False)
    cause = Column(String)                       # null for TELEMETRY_OUTAGE (a data-quality event)
    kind = Column(String, nullable=False)
    route_id = Column(String, ForeignKey("routes.id"))
    segment_waypoint_id = Column(String, ForeignKey("route_waypoints.id"))
    shipment_id = Column(String, ForeignKey("shipments.id"))
    start_at = Column(DateTime, nullable=False)
    dur_min_h = Column(Float, nullable=False)
    dur_mode_h = Column(Float, nullable=False)
    dur_max_h = Column(Float, nullable=False)
    multiplier = Column(Float, nullable=False, default=1.0)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    ended_at = Column(DateTime)
    __table_args__ = (CheckConstraint(_in("kind", KINDS)), CheckConstraint("status IN ('ACTIVE', 'ENDED')"),
                      CheckConstraint("dur_min_h <= dur_mode_h AND dur_mode_h <= dur_max_h AND dur_min_h >= 0"),
                      CheckConstraint("multiplier >= 1"))


class DelayEvent(Base, Stamp):
    __tablename__ = "delay_events"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(String, ForeignKey("shipments.id"), nullable=False, index=True)
    cause = Column(String, nullable=False, index=True)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    hours = Column(Float, nullable=False)
    __table_args__ = (CheckConstraint(_in("cause", CAUSES)), CheckConstraint("hours >= 0"))


class Prediction(Base, Stamp):
    """Immutable: rows are only ever inserted."""
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(String, ForeignKey("shipments.id"), nullable=False)
    created_sim_at = Column(DateTime, nullable=False)
    seed = Column(Integer, nullable=False)
    n = Column(Integer, nullable=False)
    p10_at = Column(DateTime, nullable=False)
    p50_at = Column(DateTime, nullable=False)
    p90_at = Column(DateTime, nullable=False)
    p_late = Column(Float, nullable=False)
    p_stockout = Column(Float)
    risk_index = Column(Integer, nullable=False)
    risk_category = Column(String, nullable=False)
    previous_p50_at = Column(DateTime)
    trigger = Column(String, nullable=False)
    trigger_event_id = Column(String)
    reasons_json = Column(JSON, nullable=False)
    data_confidence = Column(String, nullable=False)
    state_version = Column(Integer, nullable=False)
    assumptions_version = Column(Integer, nullable=False)
    __table_args__ = (Index("ix_pred_shipment_id_id", "shipment_id", "id"),)


class CustomerInventory(Base, Stamp):
    __tablename__ = "customer_inventory"
    id = Column(Integer, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    product_code = Column(String, nullable=False)
    inventory_tonnes = Column(Float, nullable=False)
    measured_at = Column(DateTime, nullable=False)
    consumption_tph = Column(Float, nullable=False)
    unloading_hours = Column(Float, nullable=False)
    min_priority_qty_tonnes = Column(Float, nullable=False, default=0.0)
    __table_args__ = (UniqueConstraint("customer_id", "product_code"), CheckConstraint("consumption_tph > 0"),
                      CheckConstraint("inventory_tonnes >= 0"), CheckConstraint("unloading_hours >= 0"))


class Alert(Base, Stamp):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    audience_role = Column(String, nullable=False, index=True)   # COORDINATOR (all of them) | CUSTOMER
    customer_id = Column(String, ForeignKey("customers.id"))
    shipment_id = Column(String, ForeignKey("shipments.id"), index=True)
    order_id = Column(String, ForeignKey("orders.id"))
    kind = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    suggested_action = Column(Text, nullable=False, default="")
    data_json = Column(JSON, nullable=False, default=dict)
    dedupe_key = Column(String, unique=True, nullable=False)
    read = Column(Boolean, nullable=False, default=False)
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    escalated_at = Column(DateTime)
    escalation_level = Column(Integer, nullable=False, default=0)
    created_sim_at = Column(DateTime, nullable=False)
    __table_args__ = (CheckConstraint("severity IN ('INFO', 'MEDIUM', 'HIGH', 'CRITICAL')"),)


class Intervention(Base, Stamp):
    """One decision case per shipment."""
    __tablename__ = "interventions"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(String, ForeignKey("shipments.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="AWAITING_APPROVAL", index=True)
    recommendation_code = Column(String, nullable=False)
    recommendation_json = Column(JSON, nullable=False)
    stability_json = Column(JSON)
    constraints_json = Column(JSON, nullable=False)
    context_json = Column(JSON, nullable=False, default=dict)
    shipment_state_version = Column(Integer, nullable=False)
    assumptions_version = Column(Integer, nullable=False)
    clock_version = Column(Integer, nullable=False)
    created_sim_at = Column(DateTime, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    selected_scenario_id = Column(Integer)
    decided_by = Column(Integer, ForeignKey("users.id"))
    decided_sim_at = Column(DateTime)
    override_reason = Column(Text)
    is_override = Column(Boolean, nullable=False, default=False)
    impact_json = Column(JSON)                  # Panel A: model expectations at approval time
    __table_args__ = (CheckConstraint(
        "status IN ('AWAITING_APPROVAL', 'APPROVED', 'REJECTED', 'SUPERSEDED', 'APPLIED', 'COMPLETED')"),)


class InterventionScenario(Base, Stamp):
    __tablename__ = "intervention_scenarios"
    id = Column(Integer, primary_key=True)
    intervention_id = Column(Integer, ForeignKey("interventions.id"), nullable=False, index=True)
    code = Column(String, nullable=False)
    eligible = Column(Boolean, nullable=False)
    ineligible_reason = Column(Text, nullable=False, default="")
    feasible = Column(Boolean, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    violations_json = Column(JSON, nullable=False)
    plan_json = Column(JSON, nullable=False, default=dict)   # what to apply (alt route, quantities)
    __table_args__ = (CheckConstraint("code IN ('CONTINUE', 'REROUTE', 'SPLIT')"),)


class AuditEvent(Base):
    """Append-only. Nothing in the code updates or deletes these rows."""
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"))
    actor_role = Column(String, nullable=False)
    action = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    before_json = Column(JSON)
    after_json = Column(JSON)
    sim_time = Column(DateTime, nullable=False)
    wall_time = Column(DateTime, server_default=func.now(), nullable=False)


class SimulationState(Base, Stamp):
    """The single source of time."""
    __tablename__ = "simulation_state"
    id = Column(Integer, primary_key=True)
    sim_now = Column(DateTime, nullable=False)
    speed = Column(Float, nullable=False, default=1.0)
    paused = Column(Boolean, nullable=False, default=True)
    clock_version = Column(Integer, nullable=False, default=1)
    global_seed = Column(Integer, nullable=False)
    next_seq = Column(Integer, nullable=False, default=1)   # deterministic id counter


class BusinessAssumptions(Base, Stamp):
    __tablename__ = "business_assumptions"
    id = Column(Integer, primary_key=True)
    values_json = Column(JSON, nullable=False)
    assumptions_version = Column(Integer, nullable=False, default=1)


BOOKING_STATUSES = ("BOOKED", "CHECKED_IN", "COMPLETED", "CANCELLED", "MISSED")


class GateSlot(Base, Stamp):
    """One hourly appointment window at the Plant X gate (simulated time, stored in UTC)."""
    __tablename__ = "gate_slots"
    id = Column(Integer, primary_key=True)
    slot_start = Column(DateTime, nullable=False, unique=True)
    slot_end = Column(DateTime, nullable=False)
    capacity = Column(Integer, nullable=False)
    closed = Column(Boolean, nullable=False, default=False)      # unavailable (e.g. maintenance)
    note = Column(String, nullable=False, default="")
    __table_args__ = (CheckConstraint("capacity >= 0 AND capacity <= 50"),)


class GateBooking(Base, Stamp):
    """Appointment lifecycle, separate from the shipment lifecycle:
    BOOKED -> CHECKED_IN -> COMPLETED, plus CANCELLED and MISSED."""
    __tablename__ = "gate_bookings"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(String, ForeignKey("shipments.id"), nullable=False, index=True)
    slot_id = Column(Integer, ForeignKey("gate_slots.id"), nullable=False, index=True)
    transporter_id = Column(String, ForeignKey("transporters.id"), nullable=False)
    driver_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    vehicle_label = Column(String, nullable=False)
    status = Column(String, nullable=False, default="BOOKED", index=True)
    created_sim_at = Column(DateTime, nullable=False)
    checked_in_at = Column(DateTime)
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancel_reason = Column(Text)
    rescheduled_from_slot_id = Column(Integer)
    __table_args__ = (
        CheckConstraint(_in("status", BOOKING_STATUSES)),
        # at most one ACTIVE booking per shipment (enforced by the database as well as by the service)
        Index("uq_gate_active_booking", "shipment_id", unique=True,
              sqlite_where=text("status IN ('BOOKED', 'CHECKED_IN')")),
    )


class Document(Base, Stamp):
    """Metadata of an uploaded invoice or proof of delivery. The file itself lives in private storage
    under a generated name; this row is the only way to reach it (and every access is checked)."""
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)                        # INVOICE | POD
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    shipment_id = Column(String, ForeignKey("shipments.id"), index=True)   # POD only
    version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False)                      # ISSUED | UPLOADED | VERIFIED | SUPERSEDED
    original_filename = Column(String, nullable=False)           # sanitised, display only
    stored_name = Column(String, nullable=False, unique=True)    # generated; never derived from user input
    content_type = Column(String, nullable=False)                # detected from the file content
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False)
    invoice_number = Column(String)
    recipient_name = Column(String)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_sim_at = Column(DateTime, nullable=False)
    delivered_sim_at = Column(DateTime)
    replaces_document_id = Column(Integer)
    replace_reason = Column(Text)
    verified_by = Column(Integer, ForeignKey("users.id"))
    verified_sim_at = Column(DateTime)
    __table_args__ = (CheckConstraint("kind IN ('INVOICE', 'POD')"), CheckConstraint("size_bytes > 0"),
                      CheckConstraint("status IN ('ISSUED', 'UPLOADED', 'VERIFIED', 'SUPERSEDED')"))
