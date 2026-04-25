"""Color classifier should distinguish red from brown, etc."""

from __future__ import annotations

import pytest

from sinuca_counter.rules.state import BallColor
from sinuca_counter.vision.classifier import ColorClassifier
from sinuca_counter.vision.palette import PaletteCalibrator


@pytest.fixture
def classifier() -> ColorClassifier:
    return ColorClassifier(PaletteCalibrator.default())


@pytest.mark.parametrize(
    "hsv,expected",
    [
        ((0, 0, 245), BallColor.BRANCA),
        ((28, 220, 230), BallColor.AMARELA),
        ((0, 220, 180), BallColor.VERMELHA),
        ((60, 200, 120), BallColor.VERDE),
        ((110, 220, 180), BallColor.AZUL),
        ((160, 160, 220), BallColor.ROSA),
        ((0, 0, 30), BallColor.PRETA_BOLA_7),
    ],
)
def test_classifier_recovers_each_color(
    classifier: ColorClassifier,
    hsv: tuple[int, int, int],
    expected: BallColor,
) -> None:
    assert classifier.classify(hsv) is expected


def test_palette_with_no_samples_raises() -> None:
    palette = PaletteCalibrator(samples={})
    with pytest.raises(ValueError):
        ColorClassifier(palette)


def test_palette_save_load(tmp_path) -> None:
    palette = PaletteCalibrator.default()
    path = tmp_path / "p.json"
    palette.save(path)
    reloaded = PaletteCalibrator.load(path)
    assert set(reloaded.samples.keys()) == set(palette.samples.keys())


def test_palette_add_sample() -> None:
    palette = PaletteCalibrator(samples={})
    palette.add_sample(BallColor.AMARELA, (28, 200, 220))
    assert palette.samples[BallColor.AMARELA.value] == [[28, 200, 220]]
