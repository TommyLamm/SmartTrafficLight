import pytest

import smart_traffic.state as state

from smart_traffic.services import digital_twin


def _fake_clock(monkeypatch, start=1000, step=200):
    current = {"t": start - step}

    def _now_ms():
        current["t"] += step
        return current["t"]

    monkeypatch.setattr(digital_twin, "_now_ms", _now_ms)


def test_start_recording_validates_max_frames():
    with pytest.raises(ValueError):
        digital_twin.start_recording(max_frames=10)

    with pytest.raises(ValueError):
        digital_twin.start_recording(max_frames="bad")


def test_capture_snapshot_and_compare_workflow(monkeypatch):
    _fake_clock(monkeypatch, start=1000, step=200)
    digital_twin.start_recording(max_frames=120)

    for idx in range(20):
        state.sys_state["persons"] = idx % 4
        state.sys_state["cars"] = 3 + (idx % 3)
        state.sys_state["wheelchairs"] = 1 if idx % 5 == 0 else 0
        state.sys_state["lane_counts"] = [idx % 3, 1, (idx + 1) % 3]
        state.sys_state["tidal_direction"] = "BALANCED"
        digital_twin.capture_snapshot("car")

    frames = digital_twin.get_frames(limit=120)
    assert len(frames) == 20
    assert frames[0]["source"] == "car"

    compare = digital_twin.run_what_if_compare(["baseline", "balanced_flow"])
    assert compare["success"] is True
    assert compare["frames_used"] == 20
    assert len(compare["strategies"]) == 2
    assert compare["winner"] in {"baseline", "balanced_flow"}


def test_compare_requires_minimum_frames(monkeypatch):
    _fake_clock(monkeypatch, start=5000, step=200)
    digital_twin.start_recording(max_frames=100)

    for _ in range(5):
        digital_twin.capture_snapshot("person")

    with pytest.raises(ValueError):
        digital_twin.run_what_if_compare()

