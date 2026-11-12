"""Sequential stock model (spec 4.6). Affects consequence, never travel time."""
import numpy as np

from .contracts import StockParams


def stockout_hours(lots: list[tuple[np.ndarray, float]], stock: StockParams) -> np.ndarray:
    """Per-sample stock-out hours for any number of lots in any arrival order.

    lots: [(arrival samples T (N,), quantity tonnes)].
    Usable arrival A = T + unloading. Walk the lots in order of A:
        stockout += max(0, A - cover_end); cover_end = max(cover_end, A) + q / r
    """
    a = np.stack([np.asarray(t, dtype=float) + stock.unload_h for t, _ in lots], axis=1)  # (N, L)
    q = np.array([qty for _, qty in lots], dtype=float)
    order = np.argsort(a, axis=1, kind="stable")
    n = a.shape[0]
    cover_end = np.full(n, float(stock.depletion_rel_h))
    out = np.zeros(n)
    rows = np.arange(n)
    for pos in range(a.shape[1]):
        idx = order[:, pos]
        arr = a[rows, idx]
        out += np.maximum(0.0, arr - cover_end)
        cover_end = np.maximum(cover_end, arr) + q[idx] / stock.rate_tph
    return out
