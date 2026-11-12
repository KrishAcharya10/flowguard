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
        "code": "flood-reroute", "number": 1, "title": "Flood on the road: reroute the truck",
        "tagline": "The main story. Spot the delay early, see why, compare the options, a person approves, everyone is told.",
        "question": "A flood will make a truck late and the customer's factory may run out of material. What should we do?", "minutes": 6,
        "proves": ["O1", "O2", "O3", "O4", "O5", "D1", "D2", "D3", "D4"],
        "focus_shipment": "SHP-PTH-1116-01",
        "story": "Truck SHP-PTH-1116-01 carries 24 tonnes of polypropylene from Plant X (Waluj) to Sharma Mouldings in Pithampur. "
                 "It is promised for 17:00 IST, and the customer has only 12.5 hours of material left. Then the Tapi River Bridge "
                 "on the road floods. Will the truck be late? Will the customer's machines stop? What should the control tower do?",
        "tabs": ["Coordinator: coordinator", "Customer: customer_a", "Driver: driver1"],
        "steps": [
            _step("Customer", "Log in as customer_a. Look at order ORD-PTH-1116-01.",
                  "Original promise 16 Nov 17:00 IST, 'Delay risk: Low'.", "/customer"),
            _step("Driver", "Log in as driver1. Press 'Confirm: Loaded, waiting at plant gate'.",
                  "'Milestone recorded.' The coordinator sees SHP-PTH-1116-01 at the plant gate.", "/driver", auto=True),
            _step("Coordinator", "Control Tower → Disruption injector → 'Flooding - Tapi River Bridge (Waluj to Pithampur road)' "
                  "→ Inject disruption.",
                  "SHP-PTH-1116-01 turns High: P(late) 100%, P(stock-out) 95%. A red closure appears on the map.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-PTH-1116-01.",
                  "'P50 moved +5.4 h … flooding event'. Biggest reason chip: 'Road closure wait'. "
                  "Stock runs out 1.5 h after the promise.", "/shipments/SHP-PTH-1116-01"),
            _step("Coordinator", "Open the Alerts drawer.",
                  "'Suggested action: REROUTE via Dhule Bypass. Modelled P(late) falls from 100% to 20%…'.", "/tower"),
            _step("Coordinator", "Open War Room → Run scenarios.",
                  "RECOMMENDED: REROUTE. Continue violates the 10% stock-out limit; Split cannot reach in time. "
                  "Reroute Rs 12,095 vs Continue Rs 1,76,660. STABLE: holds in 16 of 16 stress cases.",
                  "/shipments/SHP-PTH-1116-01/war-room"),
            _step("Coordinator", "Press 'Approve Reroute'.",
                  "'Reroute approved and applied. The customer has been notified.'", "/shipments/SHP-PTH-1116-01/war-room"),
            _step("Customer", "Refresh.",
                  "Original promise beside 'Updated expected delivery' (≈16:15 IST). 'Rerouting has been initiated'. "
                  "No costs anywhere.", "/customer"),
            _step("Driver", "Refresh.", "'Route change approved: follow Dhule Bypass.'", "/driver"),
            _step("Coordinator", "Analytics → Business impact, then Audit trail.",
                  "Panel A: ≈2.8 modelled late hours avoided (labelled MODELLED). Audit shows every step.", "/analytics"),
        ],
        "takeaway": "Tracking tells you where the truck is. FlowGuard tells you whether it matters and what to do.",
    },
    {
        "code": "late-not-costly", "number": 2, "title": "Same flood, but plenty of stock: do nothing",
        "tagline": "Late is not always costly, so the tool can say: do not spend money.",
        "question": "Another truck is stuck in the same flood. Is it worth paying to reroute it?", "minutes": 3,
        "proves": ["O3", "O4", "D2", "D3"],
        "focus_shipment": "SHP-PTH-1116-02",
        "story": "SHP-PTH-1116-02 goes to the same customer on the same flooded road, but it carries HDPE, and Sharma Mouldings "
                 "holds 80 hours of it. The late penalty is small. The truck will be late, but is rerouting worth the money?",
        "tabs": ["Coordinator: coordinator", "Customer: customer_a"],
        "steps": [
            _step("Coordinator", "Inject 'Flooding - Tapi River Bridge (Waluj to Pithampur road)'.",
                  "SHP-PTH-1116-02 turns High: P(late) ≈100% but P(stock-out) 0%.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-PTH-1116-02 → War Room → Run scenarios.",
                  "NO JUSTIFIED INTERVENTION - CONTINUE CURRENT PLAN. 'Late is not the same as costly.' "
                  "Continue Rs 7,175 vs Reroute Rs 8,564: rerouting costs more than the lateness.",
                  "/shipments/SHP-PTH-1116-02/war-room"),
            _step("Coordinator", "Compare with use case 1.",
                  "Same flood, same road; the answer changes because the customer's stock and penalty differ."),
            _step("Customer", "Log in as customer_a. Look at ORD-PTH-1116-02.",
                  "Honest 'Updated expected delivery' later than the promise; 'monitoring the shipment closely'.",
                  "/customer"),
        ],
        "takeaway": "A good control tower also tells you when NOT to act.",
    },
    {
        "code": "no-feasible", "number": 3, "title": "Strict rules, no option allowed: a person decides",
        "tagline": "The tool never recommends something that breaks a rule. A person must decide, and write down why.",
        "question": "Management sets strict limits and no option meets them. Who decides, and how is it recorded?", "minutes": 4,
        "proves": ["O4", "D2", "D4"],
        "focus_shipment": "SHP-PTH-1116-01",
        "story": "Management tightens the rules: stock-out risk at most 1% and extra freight at most Rs 20,000. "
                 "With the flood, no option can satisfy both.",
        "tabs": ["Coordinator: coordinator", "Coordinator 2: coordinator2 (optional)"],
        "steps": [
            _step("Coordinator", "Driver milestone + flood as in use case 1.", "SHP-PTH-1116-01 High.", "/tower", auto=True),
            _step("Coordinator", "Analytics → Assumptions: alpha = 0.01, max incremental freight = 20000 → Save.",
                  "'Saved as version 2 … predictions recalculated; open War Room cases superseded.'",
                  "/analytics", auto=True),
            _step("Coordinator", "SHP-PTH-1116-01 → War Room → Run scenarios.",
                  "Red banner 'NO FEASIBLE OPTION - ESCALATE'. Each option lists the rule it breaks. Reroute is "
                  "shown as 'least-violating (info only)', never 'Recommended'.", "/shipments/SHP-PTH-1116-01/war-room"),
            _step("Coordinator", "Open the Alerts drawer (also as coordinator2).",
                  "CRITICAL alert 'NO FEASIBLE OPTION - ESCALATE' for every coordinator.", "/tower"),
            _step("Coordinator", "Try to approve Reroute without a reason, then type a reason and approve.",
                  "The button stays disabled until a reason is written. After approval the case shows "
                  "'CONSTRAINT OVERRIDE - reason: …'.", "/shipments/SHP-PTH-1116-01/war-room"),
            _step("Coordinator", "Analytics → Audit trail.",
                  "A highlighted 'CONSTRAINT OVERRIDE' row with the reason and the broken rules.", "/analytics"),
        ],
        "takeaway": "Hard rules are enforced by the software; exceptions are human, written down and audited.",
    },
    {
        "code": "split", "number": 4, "title": "Truck late at the plant, no other road: split the load",
        "tagline": "Send the urgent part on a second truck so the customer's machines keep running.",
        "question": "The truck is late before it even leaves and there is no other road. How do we protect the customer?", "minutes": 5,
        "proves": ["O3", "O4", "D2", "D3"],
        "focus_shipment": "SHP-BHW-1116-03",
        "story": "SHP-BHW-1116-03 carries 20 tonnes of bottle-cap material to Sahyadri Packaging's Bhiwandi warehouse. Loading should start at "
                 "07:00 IST, but the assigned truck will be 4 hours late. The customer has only 10 hours of material left, and the "
                 "Waluj to Bhiwandi road has no alternative route, so rerouting is not possible.",
        "tabs": ["Coordinator: coordinator", "Customer: customer_c", "Relief driver: relief_tr1"],
        "steps": [
            _step("Customer", "Log in as customer_c. Look at ORD-BHW-1116-03.", "Delay risk Low.", "/customer"),
            _step("Coordinator", "Disruption injector → 'Late dispatch', shipment SHP-BHW-1116-03, tick 'Custom duration' "
                  "and enter 4 / 4 / 4 hours → Inject.",
                  "SHP-BHW-1116-03 turns High: P(late) ≈97%, P(stock-out) 100%.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-BHW-1116-03 → War Room → Run scenarios.",
                  "Reroute greyed: 'No alternative route is defined'. RECOMMENDED: SPLIT - 6 t urgent on a second "
                  "vehicle. P(stock-out) 100% → 4%. Split Rs 34,847 vs Continue Rs 1,53,897. STABLE 16/16.",
                  "/shipments/SHP-BHW-1116-03/war-room"),
            _step("Coordinator", "Approve Split.",
                  "SHP-BHW-1116-03 becomes 'Split parent' (excluded from KPIs). New lots SHP-BHW-1116-03-U (6 t, second vehicle) "
                  "and SHP-BHW-1116-03-R (14 t, original truck, still 4 h late).", "/shipments/SHP-BHW-1116-03"),
            _step("Relief driver", "Log in as relief_tr1.",
                  "The urgent lot SHP-BHW-1116-03-U is assigned to this separate driver.", "/driver"),
            _step("Customer", "Refresh.",
                  "The order now shows two deliveries; 'an urgent part has been prioritised'.", "/customer"),
        ],
        "takeaway": "When rerouting cannot help, a partial delivery protects the customer at a known cost.",
    },
    {
        "code": "breakdown", "number": 5, "title": "A truck breaks down on the road",
        "tagline": "A breakdown stops one truck. It does not close the road for the others.",
        "question": "One truck breaks down. How late will it be, and does it affect other trucks on the same road?", "minutes": 3,
        "proves": ["O2", "O3", "O4"],
        "focus_shipment": "SHP-AMV-1116-05",
        "story": "SHP-AMV-1116-05 has just left for Vidarbha Flexi Films in Amravati when its truck breaks down. "
                 "The repair is expected to take 1 to 4 hours.",
        "tabs": ["Coordinator: coordinator", "Customer: customer_b"],
        "steps": [
            _step("Coordinator", "Disruption injector → 'Vehicle breakdown', shipment SHP-AMV-1116-05 → Inject.",
                  "SHP-AMV-1116-05's ETA moves later; its new top reason chip is 'Vehicle repair wait'.", "/tower", auto=True),
            _step("Coordinator", "Open SHP-AMV-1116-05.",
                  "The chip 'Vehicle repair wait' ≈ +2.3 h; 'Road closure wait' stays 0.", "/shipments/SHP-AMV-1116-05"),
            _step("Coordinator", "Open SHP-AMV-1116-01 (same road, another truck).",
                  "Its ETA did not change: a breakdown is a vehicle stoppage, not a road closure.", "/shipments/SHP-AMV-1116-01"),
            _step("Coordinator", "SHP-AMV-1116-05 → War Room → Run scenarios.",
                  "NO JUSTIFIED INTERVENTION: the customer has 50 h of material and a low penalty, so Continue (Rs 7,304) beats Reroute "
                  "(Rs 18,819). Split is greyed: the truck has already left the plant. STABLE.",
                  "/shipments/SHP-AMV-1116-05/war-room"),
        ],
        "takeaway": "Different disruptions are modelled differently, and the reason is always visible.",
    },
    {
        "code": "lost-signal", "number": 6, "title": "GPS signal lost: show the uncertainty",
        "tagline": "We never invent a position. Old data widens the arrival range and raises an alert.",
        "question": "A truck stopped reporting its position. What do we show instead of guessing?", "minutes": 3,
        "proves": ["O2", "O3", "O4"],
        "focus_shipment": "SHP-AMV-1116-04",
        "story": "High-priority truck SHP-AMV-1116-04, going to Vidarbha Flexi Films in Amravati, stopped reporting its position 1.5 hours ago.",
        "tabs": ["Coordinator: coordinator"],
        "steps": [
            _step("Coordinator", "Look at the map and the table.",
                  "SHP-AMV-1116-04 is drawn faded and dashed; the table shows 'Data: Stale'.", "/tower"),
            _step("Coordinator", "Hover SHP-AMV-1116-04 on the map.",
                  "'Last reported … min ago - stale: last REPORTED position'.", "/tower"),
            _step("Coordinator", "Open SHP-AMV-1116-04.",
                  "Note 'telemetry is … min old; uncertainty widened'. The P10-P90 range is wider.",
                  "/shipments/SHP-AMV-1116-04"),
            _step("Coordinator", "Open the Alerts drawer.",
                  "'Stale position data: SHP-AMV-1116-04 (high priority)' - suggested: contact the transporter.", "/tower"),
            _step("Coordinator", "Advance the clock +15 min.",
                  "Other trucks move on the map; SHP-AMV-1116-04 stays at its last reported point.", "/tower", auto=True),
        ],
        "takeaway": "Being honest about what we do not know is part of responsible AI.",
    },
    {
        "code": "day-unfolds", "number": 7, "title": "Watch the day: trucks arrive and deliveries are completed",
        "tagline": "Time is simulated. Move the clock and every role sees the same update.",
        "question": "What happens when trucks reach the customer, and how is a delivery finished?", "minutes": 5,
        "proves": ["O1", "O2", "O5"],
        "focus_shipment": "SHP-AMV-1116-01",
        "story": "Fast-forward the morning. Trucks load, leave and arrive. A delivery is finished only when someone records who received it. "
                 "The driver does it on the phone, or the control tower does it for the driver.",
        "tabs": ["Coordinator: coordinator", "Driver: driver3", "Customer: customer_b"],
        "steps": [
            _step("Coordinator", "Advance the clock +4 h, then +1 h, then +1 h (6 hours in total).",
                  "Most trucks reach 'Arrived, POD pending'; markers move along the routes; SHP-PTH-1116-01/G2 leave the plant.", "/tower", auto=True),
            _step("Driver", "Log in as driver3 (Imran Shaikh, SHP-AMV-1116-01). At the top you will see 'You have arrived. Hand over the delivery'. "
                  "Type who received it, choose docs/demo_files/sample_pod_photo.png, then press 'Upload proof of delivery'. "
                  "No document? Press 'Complete delivery without a document'.",
                  "'Delivered. Received by …'.", "/driver"),
            _step("Coordinator", "Optional: another load is waiting too. Open Documents (or press 'Add proof of delivery' on its row in the table). "
                  "Type the receiver's name and press 'Complete without a document' (or upload the file).",
                  "The delivery is completed for the driver and the history says 'recorded by the control tower'.", "/documents"),
            _step("Customer", "Log in as customer_b.", "ORD-AMV-1116-01 shows 'Delivered'.", "/customer"),
            _step("Coordinator", "Analytics → Performance.",
                  "Arrived orders and on-time % now include today's arrivals (on-time is judged at gate arrival, "
                  "not at proof of delivery).", "/analytics"),
        ],
        "takeaway": "One shared, live view for coordinator, customer and driver.",
    },
    {
        "code": "dashboard-privacy", "number": 8, "title": "Dashboard insights and who can see what",
        "tagline": "The performance dashboard (8 weeks of sample history) and role-based privacy.",
        "question": "Which routes and transporters cause delays? And can a customer see anything they should not?", "minutes": 4,
        "proves": ["O1", "O5"],
        "focus_shipment": "",
        "story": "Which routes and transporters cause delays, and why? And can a customer ever see another "
                 "customer's data or our internal costs?",
        "tabs": ["Coordinator: coordinator", "Customer: customer_b"],
        "steps": [
            _step("Coordinator", "Analytics → Performance.",
                  "On-time ≈86% over 161 arrived orders. Waluj to Amravati is weakest (≈76%) and its delays are mostly "
                  "'Route congestion'. Konkan Express Logistics is the weakest transporter, with many breakdowns on "
                  "Waluj to Satara.", "/analytics"),
            _step("Coordinator", "Analytics → Responsible AI.",
                  "Where AI is and is not used; the controls.", "/analytics"),
            _step("Customer", "Log in as customer_b.",
                  "Only Vidarbha Flexi Films' own orders. No costs, penalties, risk weights or transporter names.", "/customer"),
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
    "flood-reroute": lambda db, u: (_milestone(db, "SHP-PTH-1116-01", "AT_PLANT_GATE"), _disrupt(db, u, "FLOOD_R1")),
    "late-not-costly": lambda db, u: _disrupt(db, u, "FLOOD_R1"),
    "no-feasible": lambda db, u: (_milestone(db, "SHP-PTH-1116-01", "AT_PLANT_GATE"), _disrupt(db, u, "FLOOD_R1"),
                                  _assume(db, u, alpha=0.01, max_incremental_freight_rs=20000.0)),
    "split": lambda db, u: _disrupt(db, u, "LATE_DISPATCH", "SHP-BHW-1116-03", (4.0, 4.0, 4.0)),
    "breakdown": lambda db, u: _disrupt(db, u, "BREAKDOWN", "SHP-AMV-1116-05"),
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
