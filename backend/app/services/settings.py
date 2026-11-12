"""Editable assumptions: one code path for the API and the demo guide."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .. import models as m
from ..assumptions import Assumptions
from . import predictions as pred_svc
from . import warroom as wr
from .core import audit


def update_assumptions(db: Session, new: Assumptions, user: Optional[m.User]) -> tuple[int, int, int]:
    """Bump assumptions_version, supersede open War Room cases, recalculate every active prediction,
    write an audit event. Returns (version, predictions_recomputed, cases_superseded). Does not commit."""
    row = db.get(m.BusinessAssumptions, 1)
    before = dict(row.values_json)
    after = new.model_dump()
    changed = {k: {"from": before.get(k), "to": v} for k, v in after.items() if before.get(k) != v}
    row.values_json = after
    row.assumptions_version += 1
    db.flush()
    superseded = wr.supersede_open_cases(db, "assumptions changed", user)
    n = pred_svc.recompute(db, trigger="ASSUMPTIONS_CHANGE", trigger_event_id=f"AV-{row.assumptions_version}",
                           trigger_label=f"assumptions v{row.assumptions_version}")
    audit(db, user, "ASSUMPTIONS_UPDATED", "business_assumptions", 1, before={"version": row.assumptions_version - 1},
          after={"version": row.assumptions_version, "changed": changed})
    return row.assumptions_version, n, superseded
