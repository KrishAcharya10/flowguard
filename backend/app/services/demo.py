"""Demo guide: ready-made use cases for presenting FlowGuard (DEMO_MODE only).

Each use case has a story, the requirements it proves, step-by-step instructions (which tab, what to do,
what you should see) and two setup modes:
  start - reset the demo data to the seeded starting state; the presenter performs every step live;
  jump  - reset, then perform the "setup" steps automatically (driver milestone, disruption, assumption
          change, clock advance) so the presenter lands straight on the decision point.

"Jump" uses the SAME service functions as the real buttons, so nothing is faked: every change creates the
normal events, predictions, alerts and audit entries (performed by the logged-in coordinator, or by the
assigned driver for milestones).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import config
from .. import models as m
from ..assumptions import Assumptions
from ..db import SessionLocal
from . import disruptions as dis_svc
from . import predictions as pred_svc
from . import settings
from .core import audit, get_assumptions, sim_now
from .shipments import advance_state

P = "PlantX-demo-2026"


def _step(tab: str, do: str, see: str = "", link: str = "", auto: bool = False) -> dict:
    return {"tab": tab, "do": do, "see": see, "link": link, "auto": auto}


USE_CASES: list[dict] = [
    {
        "code": "flood-reroute", "number": 1, "title": "Flood on the road, customer about to run out → Reroute",
        "tagline": "The main story: predict the delay, explain it, compare options, a human approves, everyone is told.",
        "proves": ["O1", "O2", "O3", "O4", "O5", "D1", "D2", "D3", "D4"],
        "focus_shipment": "SHP-G1",
        "story": "Truck SHP-G1 carries 24 t of PP to Northfield Mouldings, promised for 17:00 IST. Northfield has "
                 "only 12.5 hours of stock left. A river crossing on the North Corridor floods. Will the truck be "
                 "late, will the customer's line stop, and what should we do?",
        "tabs": ["Coordinator: coordinator", "Customer: customer_a", "Driver: driver1"],
        "steps": [
            _step("Customer", "Log in as customer_a. Look at order ORD-G1.",
                  "Original promise 16 Nov 17:00 IST, 'Delay risk: Low'.", "/customer"),
            _step("Driver", "Log in as driver1. Press 'Confirm: Loaded, waiting at plant gate'.",
                  "'Milestone recorded.' The coordinator sees SHP-G1 at the plant gate.", "/driver", auto=True),
            _step("Coordinator", "Control Tower → Disruption injector → 'Flooding - North Corridor river crossing' "
                  "→ Inject disruption.",
                  "SHP-G1 turns High: P(late) 100%, P(stock-out) 95%. A red closure appears on the map.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-G1.",
                  "'P50 moved +5.4 h … flooding event'. Biggest reason chip: 'Road closure wait'. "
                  "Stock runs out 1.5 h after the promise.", "/shipments/SHP-G1"),
            _step("Coordinator", "Open the Alerts drawer.",
                  "'Suggested action: REROUTE via North Bypass. Modelled P(late) falls from 100% to 20%…'.", "/tower"),
            _step("Coordinator", "Open War Room → Run scenarios.",
                  "RECOMMENDED: REROUTE. Continue violates the 10% stock-out limit; Split cannot reach in time. "
                  "Reroute Rs 12,095 vs Continue Rs 1,76,660. STABLE: holds in 16 of 16 stress cases.",
                  "/shipments/SHP-G1/war-room"),
            _step("Coordinator", "Press 'Approve Reroute'.",
                  "'Reroute approved and applied. The customer has been notified.'", "/shipments/SHP-G1/war-room"),
            _step("Customer", "Refresh.",
                  "Original promise beside 'Updated expected delivery' (≈16:15 IST). 'Rerouting has been initiated'. "
                  "No costs anywhere.", "/customer"),
            _step("Driver", "Refresh.", "'Route change approved: follow North Bypass.'", "/driver"),
            _step("Coordinator", "Analytics → Business impact, then Audit trail.",
                  "Panel A: ≈2.8 modelled late hours avoided (labelled MODELLED). Audit shows every step.", "/analytics"),
        ],
        "takeaway": "Tracking tells you where the truck is. FlowGuard tells you whether it matters and what to do.",
    },
    {
        "code": "late-not-costly", "number": 2, "title": "Same flood, plenty of stock → do nothing (on purpose)",
        "tagline": "Late is not the same as costly: the tool can recommend NOT spending money.",
        "proves": ["O3", "O4", "D2", "D3"],
        "focus_shipment": "SHP-G2",
        "story": "SHP-G2 goes to the same customer on the same flooded road, but for a product where Northfield "
                 "holds 80 hours of stock and the late penalty is small. It will be late. Is rerouting worth it?",
        "tabs": ["Coordinator: coordinator", "Customer: customer_a"],
        "steps": [
            _step("Coordinator", "Inject 'Flooding - North Corridor river crossing'.",
                  "SHP-G2 turns High: P(late) ≈100% but P(stock-out) 0%.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-G2 → War Room → Run scenarios.",
                  "NO JUSTIFIED INTERVENTION - CONTINUE CURRENT PLAN. 'Late is not the same as costly.' "
                  "Continue Rs 7,175 vs Reroute Rs 8,564: rerouting costs more than the lateness.",
                  "/shipments/SHP-G2/war-room"),
            _step("Coordinator", "Compare with use case 1.",
                  "Same flood, same road; the answer changes because the customer's stock and penalty differ."),
            _step("Customer", "Log in as customer_a. Look at ORD-G2.",
                  "Honest 'Updated expected delivery' later than the promise; 'monitoring the shipment closely'.",
                  "/customer"),
        ],
        "takeaway": "A good control tower also tells you when NOT to act.",
    },
    {
        "code": "no-feasible", "number": 3, "title": "Every option breaks a rule → escalate, human override",
        "tagline": "The tool never recommends something that breaks a hard rule; a human must decide and explain.",
        "proves": ["O4", "D2", "D4"],
        "focus_shipment": "SHP-G1",
        "story": "Management tightens the rules: stock-out risk at most 1% and extra freight at most Rs 20,000. "
                 "With the flood, no option can satisfy both.",
        "tabs": ["Coordinator: coordinator", "Coordinator 2: coordinator2 (optional)"],
        "steps": [
            _step("Coordinator", "Driver milestone + flood as in use case 1.", "SHP-G1 High.", "/tower", auto=True),
            _step("Coordinator", "Analytics → Assumptions: alpha = 0.01, max incremental freight = 20000 → Save.",
                  "'Saved as version 2 … predictions recalculated; open War Room cases superseded.'",
                  "/analytics", auto=True),
            _step("Coordinator", "SHP-G1 → War Room → Run scenarios.",
                  "Red banner 'NO FEASIBLE OPTION - ESCALATE'. Each option lists the rule it breaks. Reroute is "
                  "shown as 'least-violating (info only)', never 'Recommended'.", "/shipments/SHP-G1/war-room"),
            _step("Coordinator", "Open the Alerts drawer (also as coordinator2).",
                  "CRITICAL alert 'NO FEASIBLE OPTION - ESCALATE' for every coordinator.", "/tower"),
            _step("Coordinator", "Try to approve Reroute without a reason, then type a reason and approve.",
                  "The button stays disabled until a reason is written. After approval the case shows "
                  "'CONSTRAINT OVERRIDE - reason: …'.", "/shipments/SHP-G1/war-room"),
            _step("Coordinator", "Analytics → Audit trail.",
                  "A highlighted 'CONSTRAINT OVERRIDE' row with the reason and the broken rules.", "/analytics"),
        ],
        "takeaway": "Hard rules are enforced by the software; exceptions are human, written down and audited.",
    },
    {
        "code": "split", "number": 4, "title": "Truck delayed at the plant, no alternative road → Split",
        "tagline": "Send an urgent part on a second truck so the customer's line keeps running.",
        "proves": ["O3", "O4", "D2", "D3"],
        "focus_shipment": "SHP-1013",
        "story": "SHP-1013 (20 t of caps material for Southbay Packaging) should start loading at 07:00 IST, but the "
                 "assigned truck will be 4 hours late. Southbay has only 10 hours of stock. The West Link has no "
                 "alternative road, so rerouting is impossible.",
        "tabs": ["Coordinator: coordinator", "Customer: customer_c", "Relief driver: relief_tr1"],
        "steps": [
            _step("Customer", "Log in as customer_c. Look at ORD-1013.", "Delay risk Low.", "/customer"),
            _step("Coordinator", "Disruption injector → 'Late dispatch', shipment SHP-1013, tick 'Custom duration' "
                  "and enter 4 / 4 / 4 hours → Inject.",
                  "SHP-1013 turns High: P(late) ≈97%, P(stock-out) 100%.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-1013 → War Room → Run scenarios.",
                  "Reroute greyed: 'No alternative route is defined'. RECOMMENDED: SPLIT - 6 t urgent on a second "
                  "vehicle. P(stock-out) 100% → 4%. Split Rs 34,847 vs Continue Rs 1,53,897. STABLE 16/16.",
                  "/shipments/SHP-1013/war-room"),
            _step("Coordinator", "Approve Split.",
                  "SHP-1013 becomes 'Split parent' (excluded from KPIs). New lots SHP-1013-U (6 t, second vehicle) "
                  "and SHP-1013-R (14 t, original truck, still 4 h late).", "/shipments/SHP-1013"),
            _step("Relief driver", "Log in as relief_tr1.",
                  "The urgent lot SHP-1013-U is assigned to this separate driver.", "/driver"),
            _step("Customer", "Refresh.",
                  "The order now shows two deliveries; 'an urgent part has been prioritised'.", "/customer"),
        ],
        "takeaway": "When rerouting cannot help, a partial delivery protects the customer at a known cost.",
    },
    {
        "code": "breakdown", "number": 5, "title": "Truck breaks down on the road",
        "tagline": "A breakdown stops one truck where it is; it does not close the road for others.",
        "proves": ["O2", "O3", "O4"],
        "focus_shipment": "SHP-1014",
        "story": "SHP-1014 has just left for Eastgate Films on the East Corridor when its truck breaks down. "
                 "Repair is expected to take 1-4 hours.",
        "tabs": ["Coordinator: coordinator", "Customer: customer_b"],
        "steps": [
            _step("Coordinator", "Disruption injector → 'Vehicle breakdown', shipment SHP-1014 → Inject.",
                  "SHP-1014's ETA moves later; its new top reason chip is 'Vehicle repair wait'.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-1014.",
                  "The chip 'Vehicle repair wait' ≈ +2.3 h; 'Road closure wait' stays 0.", "/shipments/SHP-1014"),
            _step("Coordinator", "Open SHP-1003 (same road, another truck).",
                  "Its ETA did not change: a breakdown is a vehicle stoppage, not a road closure.", "/shipments/SHP-1003"),
            _step("Coordinator", "SHP-1014 → War Room → Run scenarios.",
                  "NO JUSTIFIED INTERVENTION: Eastgate has 50 h of stock and a low penalty, so Continue (Rs 7,304) beats Reroute "
                  "(Rs 18,819). Split is greyed: the truck has already left the plant. STABLE.",
                  "/shipments/SHP-1014/war-room"),
        ],
        "takeaway": "Different disruptions are modelled differently, and the reason is always visible.",
    },
    {
        "code": "lost-signal", "number": 6, "title": "Lost GPS signal → honest uncertainty",
        "tagline": "We never invent a position; stale data widens the ETA range and raises an alert.",
        "proves": ["O2", "O3", "O4"],
        "focus_shipment": "SHP-1010",
        "story": "High-priority truck SHP-1010 to Eastgate stopped reporting its position 1.5 hours ago.",
        "tabs": ["Coordinator: coordinator"],
        "steps": [
            _step("Coordinator", "Look at the map and the table.",
                  "SHP-1010 is drawn faded and dashed; the table shows 'Data: Stale'.", "/tower"),
            _step("Coordinator", "Hover SHP-1010 on the map.",
                  "'Last reported … min ago - stale: last REPORTED position'.", "/tower"),
            _step("Coordinator", "Open SHP-1010.",
                  "Note 'telemetry is … min old; uncertainty widened'. The P10-P90 range is wider.",
                  "/shipments/SHP-1010"),
            _step("Coordinator", "Open the Alerts drawer.",
                  "'Stale position data: SHP-1010 (high priority)' - suggested: contact the transporter.", "/tower"),
            _step("Coordinator", "Advance the clock +15 min.",
                  "Other trucks move on the map; SHP-1010 stays at its last reported point.", "/tower", auto=True),
        ],
        "takeaway": "Being honest about what we do not know is part of responsible AI.",
    },
    {
        "code": "day-unfolds", "number": 7, "title": "Watch the day unfold: trucks arrive, KPIs update",
        "tagline": "Time is simulated: advance the clock and every role's view moves together.",
        "proves": ["O1", "O2", "O5"],
        "focus_shipment": "SHP-1003",
        "story": "Fast-forward the morning. Trucks load, leave, arrive; drivers record proof of delivery.",
        "tabs": ["Coordinator: coordinator", "Driver: driver3", "Customer: customer_b"],
        "steps": [
            _step("Coordinator", "Advance the clock +4 h, then +1 h, then +1 h (6 hours in total).",
                  "Most trucks reach 'Arrived, POD pending'; markers move along the routes; SHP-G1/G2 leave the plant.", "/tower", auto=True),
            _step("Driver", "Log in as driver3 (SHP-1003). Enter a recipient name and choose docs/demo_files/sample_pod_photo.png → 'Upload proof of delivery'.",
                  "'Delivered. Received by …'.", "/driver"),
            _step("Customer", "Log in as customer_b.", "ORD-1003 shows 'Delivered'.", "/customer"),
            _step("Coordinator", "Analytics → Performance.",
                  "Arrived orders and on-time % now include today's arrivals (on-time is judged at gate arrival, "
                  "not at proof of delivery).", "/analytics"),
        ],
        "takeaway": "One shared, live view for coordinator, customer and driver.",
    },
    {
        "code": "dashboard-privacy", "number": 8, "title": "Dashboard insights + who can see what",
        "tagline": "O5 dashboard from 8 weeks of (fictional) history, and role-based privacy.",
        "proves": ["O1", "O5"],
        "focus_shipment": "",
        "story": "Which routes and transporters cause delays, and why? And can a customer ever see another "
                 "customer's data or our internal costs?",
        "tabs": ["Coordinator: coordinator", "Customer: customer_b"],
        "steps": [
            _step("Coordinator", "Analytics → Performance.",
                  "On-time ≈86% over 161 arrived orders. East Corridor is weakest (≈76%) and its delays are mostly "
                  "'Route congestion'. Coastwise Logistics is the weakest transporter, with many breakdowns on "
                  "South Coastal.", "/analytics"),
            _step("Coordinator", "Analytics → Responsible AI.",
                  "Where AI is and is not used; the controls.", "/analytics"),
            _step("Customer", "Log in as customer_b.",
                  "Only Eastgate's orders. No costs, penalties, risk weights or transporter names.", "/customer"),
            _step("Customer", "In the address bar, try /tower.",
                  "Sent back to 'My orders'. The API also refuses (403); another customer's shipment returns 404.",
                  "/tower"),
        ],
        "takeaway": "Insight for the coordinator, privacy for the customer.",
    },
]
BY_CODE = {u["code"]: u for u in USE_CASES}


# ---------- setup actions (same services as the real buttons) ----------

def _driver_of(db: Session, shipment_id: str) -> m.User:
    return db.get(m.User, db.get(m.Shipment, shipment_id).driver_user_id)


def _milestone(db: Session, shipment_id: str, to_state: str) -> None:
    sh = db.get(m.Shipment, shipment_id)
    driver = _driver_of(db, shipment_id)
    before = {"state": sh.state, "state_version": sh.state_version}
    advance_state(db, sh, to_state, sim_now(db), "DRIVER", driver)
    audit(db, driver, "MILESTONE_POSTED", "shipment", sh.id, before=before,
          after={"state": sh.state, "state_version": sh.state_version})
    db.flush()
    pred_svc.recompute(db, trigger="MILESTONE", trigger_label=f"milestone {to_state} on {sh.id}",
                       trigger_event_id=f"{sh.id}:{to_state}")


def _disrupt(db: Session, user: m.User, preset: str, shipment_id=None, duration=None) -> None:
    d = dis_svc.create(db, user, preset, shipment_id, 0.0, duration, None)
    db.flush()
    pred_svc.recompute(db, trigger="DISRUPTION_START", trigger_event_id=d.id,
                       trigger_label=f"{(d.cause or d.kind).replace('_', ' ').lower()} event {d.id}")


def _assume(db: Session, user: m.User, **changes) -> None:
    a, _ = get_assumptions(db)
    settings.update_assumptions(db, Assumptions(**{**a.model_dump(), **changes}), user)


def _advance(db: Session, user: m.User, minutes: int) -> None:
    from ..simulator import clock
    clock.advance(db, minutes, user)


JUMPS = {
    "flood-reroute": lambda db, u: (_milestone(db, "SHP-G1", "AT_PLANT_GATE"), _disrupt(db, u, "FLOOD_R1")),
    "late-not-costly": lambda db, u: _disrupt(db, u, "FLOOD_R1"),
    "no-feasible": lambda db, u: (_milestone(db, "SHP-G1", "AT_PLANT_GATE"), _disrupt(db, u, "FLOOD_R1"),
                                  _assume(db, u, alpha=0.01, max_incremental_freight_rs=20000.0)),
    "split": lambda db, u: _disrupt(db, u, "LATE_DISPATCH", "SHP-1013", (4.0, 4.0, 4.0)),
    "breakdown": lambda db, u: _disrupt(db, u, "BREAKDOWN", "SHP-1014"),
    "lost-signal": lambda db, u: _advance(db, u, 15),
    "day-unfolds": lambda db, u: _advance(db, u, 360),
    "dashboard-privacy": lambda db, u: None,
}


def setup(code: str, mode: str, username: str) -> dict:
    """Reset the demo data, optionally jump to the decision point. Runs in its own sessions."""
    if not config.DEMO_MODE:
        raise HTTPException(403, "The demo guide is only available when DEMO_MODE=true")
    if code not in BY_CODE:
        raise HTTPException(404, "Unknown use case")
    from ..seed.reset import reset
    reset()
    with SessionLocal() as db:
        user = db.query(m.User).filter(m.User.username == username).one()
        audit(db, user, "DEMO_SETUP", "use_case", code, after={"mode": mode})
        if mode == "jump":
            JUMPS[code](db, user)
        db.commit()
    uc = BY_CODE[code]
    done = sum(1 for s in uc["steps"] if s["auto"]) if mode == "jump" else 0
    return {"code": code, "mode": mode, "steps_done_automatically": done,
            "message": (f"Use case {uc['number']} ready at the decision point: {done} setup step(s) marked "
                        f"'done for you' were performed." if mode == "jump" and done else
                        f"Use case {uc['number']} ready: demo data reset to the starting state.")}
