import numpy as np
from PIL import Image

import smart_traffic.state as state

from smart_traffic.services import detect_car


class _FakeTensor:
    def __init__(self, data):
        self._data = np.asarray(data, dtype=float)

    def cpu(self):
        return self

    def numpy(self):
        return self._data

    def __len__(self):
        return len(self._data)


class _FakeBoxes:
    def __init__(self, cls_values, xyxy_values):
        self.cls = _FakeTensor(cls_values)
        self.xyxy = _FakeTensor(xyxy_values)


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes

    def plot(self):
        return np.zeros((48, 64, 3), dtype=np.uint8)


class _FakeModel:
    def __init__(self, results):
        self._results = results

    def predict(self, **kwargs):
        return self._results


def test_boundary_x_clamps_out_of_range_ratio():
    left = detect_car._boundary_x(0.2, 0.4, y=-10, image_width=100, image_height=100)
    right = detect_car._boundary_x(0.2, 0.4, y=999, image_width=100, image_height=100)

    assert left == 20.0
    assert right == 40.0


def test_compute_tidal_direction_balanced_and_biased():
    state.lane_sample_window.clear()
    assert detect_car._compute_tidal_direction() == "BALANCED"

    state.lane_sample_window.extend([[6, 0, 2], [5, 1, 2], [6, 1, 1]])
    assert detect_car._compute_tidal_direction() == "LEFT_BIAS"

    state.lane_sample_window.clear()
    state.lane_sample_window.extend([[1, 0, 5], [2, 1, 5], [1, 1, 6]])
    assert detect_car._compute_tidal_direction() == "RIGHT_BIAS"


def test_process_car_data_returns_snapshot_when_detection_disabled():
    state.sys_state["detection"] = False
    state.sys_state["cars"] = 7
    state.sys_state["lane_counts"] = [2, 3, 2]
    state.sys_state["tidal_direction"] = "BALANCED"

    payload = detect_car.process_car_data(b"ignored")

    assert payload["cars"] == 7
    assert payload["cars_total"] == 7
    assert payload["lane_counts"] == [2, 3, 2]
    assert payload["tidal_direction"] == "BALANCED"


def test_process_car_data_updates_counts_and_lane_distribution(monkeypatch):
    monkeypatch.setattr(detect_car, "decode_image", lambda _: Image.new("RGB", (100, 100)))
    monkeypatch.setattr(
        detect_car,
        "car_model",
        _FakeModel(
            [
                _FakeResult(
                    _FakeBoxes(
                        cls_values=[2, 7],
                        xyxy_values=[
                            [0, 10, 20, 90],    # lane 0
                            [80, 10, 100, 90],  # lane 2
                        ],
                    )
                )
            ]
        ),
    )

    payload = detect_car.process_car_data(b"fake-obfuscated-bytes")

    assert payload["cars"] == 2
    assert payload["cars_total"] == 2
    assert payload["lane_counts"] == [1, 0, 1]
    assert payload["tidal_direction"] == "BALANCED"
    assert payload["frame_size"] == {"width": 100, "height": 100}


def test_boundary_x_zero_size_image_returns_zero():
    """Zero-dimension image → boundary_x returns 0.0 (guard clause)."""
    assert detect_car._boundary_x(0.2, 0.4, y=50, image_width=0, image_height=100) == 0.0
    assert detect_car._boundary_x(0.2, 0.4, y=50, image_width=100, image_height=0) == 0.0
    assert detect_car._boundary_x(0.2, 0.4, y=50, image_width=0, image_height=0) == 0.0


def test_bucket_lane_zero_size_image_returns_middle():
    """Zero-dimension image → bucket_lane returns middle lane index."""
    from smart_traffic.config import CAR_LANE_REGION_COUNT
    boundaries = {
        "boundary1_top": 0.33, "boundary1_bottom": 0.33,
        "boundary2_top": 0.66, "boundary2_bottom": 0.66,
    }
    result = detect_car._bucket_lane(50, 50, 0, 0, boundaries)
    assert result == CAR_LANE_REGION_COUNT // 2


def test_boundary_x_interpolates_linearly():
    """Boundary x at mid-height should be average of top and bottom ratios."""
    # y=50 in a 100px-tall image → y_ratio = 0.5
    # x_ratio = 0.2 + (0.4 - 0.2) * 0.5 = 0.3
    # boundary_x = 0.3 * 200 = 60.0
    result = detect_car._boundary_x(0.2, 0.4, y=50, image_width=200, image_height=100)
    assert abs(result - 60.0) < 0.01

