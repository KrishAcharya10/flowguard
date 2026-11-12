"""Risk index and category (spec 4.7). A heuristic index, not a probability."""
from __future__ import annotations

ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def risk_index(p_late: float, p_stockout: float | None, w_late: float, w_stock: float) -> int:
    if p_stockout is None:          # no stock data: omit stock terms, w_late = 1
        return int(round(100 * p_late))
    return int(round(100 * (w_late * p_late + w_stock * p_stockout)))


def risk_category(index: int, p_late: float, p_stockout: float | None,
                  medium_from: int = 30, high_from: int = 60) -> str:
    band = "HIGH" if index >= high_from else "MEDIUM" if index >= medium_from else "LOW"
    floor = "LOW"
    if p_late >= 0.25:
        floor = "MEDIUM"
    if p_late >= 0.50 or (p_stockout is not None and p_stockout >= 0.30):
        floor = "HIGH"
    return band if ORDER[band] >= ORDER[floor] else floor
