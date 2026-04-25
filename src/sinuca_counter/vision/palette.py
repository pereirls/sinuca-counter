"""Palette calibration: per-colour reference HSV samples."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from sinuca_counter.rules.state import BallColor


@dataclass
class PaletteCalibrator:
    """Stores HSV reference samples for each :class:`BallColor`.

    A nearest-neighbour classifier (in HSV space, with hue treated cyclically)
    consumes this palette to label detected balls.
    """

    samples: dict[str, list[list[int]]] = field(default_factory=dict)

    @classmethod
    def default(cls) -> PaletteCalibrator:
        """Reasonable defaults so the system runs without manual calibration."""

        return cls(
            samples={
                BallColor.BRANCA.value: [[0, 0, 240]],
                BallColor.AMARELA.value: [[28, 220, 230]],
                BallColor.VERMELHA.value: [[0, 220, 180]],
                BallColor.VERDE.value: [[60, 200, 120]],
                BallColor.MARROM.value: [[15, 200, 90]],
                BallColor.AZUL.value: [[110, 220, 180]],
                BallColor.ROSA.value: [[160, 160, 220]],
                BallColor.PRETA_BOLA_7.value: [[0, 0, 30]],
            }
        )

    def add_sample(self, color: BallColor, hsv: tuple[int, int, int]) -> None:
        bucket = self.samples.setdefault(color.value, [])
        bucket.append([int(hsv[0]), int(hsv[1]), int(hsv[2])])

    def colors(self) -> list[BallColor]:
        return [BallColor(value) for value in self.samples]

    # -- persistence -------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> PaletteCalibrator:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(samples={k: [list(s) for s in v] for k, v in data.items()})

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.samples, indent=2),
            encoding="utf-8",
        )

    # -- numeric helpers for the classifier --------------------------------

    def reference_array(self) -> tuple[list[BallColor], np.ndarray]:
        """Returns parallel arrays of colours and their reference HSV samples."""

        colors: list[BallColor] = []
        rows: list[list[int]] = []
        for value, samples in self.samples.items():
            color = BallColor(value)
            for hsv in samples:
                colors.append(color)
                rows.append(list(hsv))
        if not rows:
            raise ValueError("palette has no samples")
        return colors, np.asarray(rows, dtype=np.int16)


__all__ = ["PaletteCalibrator"]
