"""Calibrator persistence + warp."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sinuca_counter.vision.calibrator import (
    TOP_DOWN_H,
    TOP_DOWN_W,
    CalibrationData,
    TableCalibrator,
)


def _square_calibration() -> CalibrationData:
    return CalibrationData(
        corners=[[0, 0], [200, 0], [200, 100], [0, 100]],
        top_down_size=(TOP_DOWN_W, TOP_DOWN_H),
    )


def test_warp_produces_top_down_size() -> None:
    calib = TableCalibrator(_square_calibration())
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    out = calib.warp(frame)
    assert out.shape == (TOP_DOWN_H, TOP_DOWN_W, 3)


def test_pocket_centers_returns_six_pockets() -> None:
    calib = _square_calibration()
    centers = calib.pocket_centers()
    assert set(centers.keys()) == {
        "top_left",
        "top_mid",
        "top_right",
        "bottom_left",
        "bottom_mid",
        "bottom_right",
    }
    assert centers["top_left"] == (0, 0)
    assert centers["bottom_right"] == (TOP_DOWN_W, TOP_DOWN_H)


def test_save_load_roundtrip(tmp_path: Path) -> None:
    calib = TableCalibrator(_square_calibration())
    path = tmp_path / "out.calib.json"
    calib.save(path)
    reloaded = TableCalibrator.load(path)
    assert reloaded.top_down_size == calib.top_down_size
    assert reloaded.calibration.corners == calib.calibration.corners


def test_invalid_corner_count_raises() -> None:
    with pytest.raises(ValueError):
        TableCalibrator(CalibrationData(corners=[[0, 0]]))
