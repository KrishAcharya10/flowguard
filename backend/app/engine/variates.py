"""Named-column variate matrix (common random numbers).

Every column is a deterministic function of (seed, column name). Any option
(Continue / Reroute / Split) that asks for the same column gets the same
numbers, so option comparisons are paired rather than noisy.
"""
import zlib

import numpy as np


class VariateMatrix:
    def __init__(self, seed: int, n: int):
        self.seed = int(seed) & 0xFFFFFFFF
        self.n = int(n)
        self._cols: dict[str, np.ndarray] = {}

    def _rng(self, name: str) -> np.random.Generator:
        return np.random.default_rng([self.seed, zlib.crc32(name.encode()) & 0xFFFFFFFF])

    def z(self, name: str) -> np.ndarray:
        """Standard normal column."""
        k = "z|" + name
        if k not in self._cols:
            self._cols[k] = self._rng(k).standard_normal(self.n)
        return self._cols[k]

    def u(self, name: str) -> np.ndarray:
        """Uniform(0,1) column."""
        k = "u|" + name
        if k not in self._cols:
            self._cols[k] = self._rng(k).random(self.n)
        return self._cols[k]
