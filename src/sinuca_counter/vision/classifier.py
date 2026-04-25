"""Nearest-neighbour colour classifier in HSV space."""

from __future__ import annotations

import numpy as np

from sinuca_counter.rules.state import BallColor

from .palette import PaletteCalibrator


def _hue_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cyclic distance on [0, 180) (OpenCV's hue range)."""

    diff = np.abs(a.astype(np.int32) - b.astype(np.int32))
    return np.minimum(diff, 180 - diff)


class ColorClassifier:
    """Classifies an HSV patch into a :class:`BallColor`."""

    def __init__(self, palette: PaletteCalibrator) -> None:
        self._colors, self._refs = palette.reference_array()

    def classify(self, hsv: tuple[int, int, int]) -> BallColor:
        sample = np.asarray(hsv, dtype=np.int16)
        h_dist = _hue_distance(self._refs[:, 0], np.full_like(self._refs[:, 0], sample[0]))
        # Saturation/value get weighted less so a slightly-darker red still
        # snaps to red instead of brown.
        sv_dist = np.abs(self._refs[:, 1:] - sample[1:]).sum(axis=1)
        # Achromatic colours (low saturation) are dominated by value (white vs
        # black). For those rows the hue is meaningless.
        achromatic = self._refs[:, 1] < 50
        score = np.where(
            achromatic,
            sv_dist * 1.5,
            h_dist.astype(np.int64) * 4 + sv_dist // 2,
        )
        winner = int(np.argmin(score))
        return self._colors[winner]


__all__ = ["ColorClassifier"]
