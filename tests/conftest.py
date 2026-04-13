import io
import sys
import time
import types
from copy import deepcopy

import numpy as np
import pytest
from PIL import Image

from smart_traffic import config as st_config


class _DummyModel:
    def predict(self, *args, **kwargs):
        return []


_fake_models = types.ModuleType("smart_traffic.models")
_fake_models.car_model = _DummyModel()
_fake_models.person_model = _DummyModel()
_fake_models.plate_model = _DummyModel()
sys.modules.setdefault("smart_traffic.models", _fake_models)


import smart_traffic.state as state  # noqa: E402
from smart_traffic.services import digital_twin  # noqa: E402


_INITIAL_SYS_STATE = deepcopy(state.sys_state)
_DEFAULT_BOUNDARIES = {
    "boundary1_top": float(st_config.LANE_BOUNDARY1_TOP_RATIO),
    "boundary1_bottom": float(st_config.LANE_BOUNDARY1_BOTTOM_RATIO),
    "boundary2_top": float(st_config.LANE_BOUNDARY2_TOP_RATIO),
    "boundary2_bottom": float(st_config.LANE_BOUNDARY2_BOTTOM_RATIO),
}


@pytest.fixture(autouse=True)
def reset_global_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        state,
        "lane_boundaries_state_path",
        str(tmp_path / "lane_boundaries_state.json"),
        raising=False,
    )
    state.lane_boundaries_state_mtime_ns = 0

    state.sys_state.clear()
    state.sys_state.update(deepcopy(_INITIAL_SYS_STATE))

    state.latest_frame = None
    state.latest_frame_person = None
    state.latest_frame_car = None
    state.latest_frame_plate = None
    state.latest_frame_ts_person = 0.0
    state.latest_frame_ts_car = 0.0
    state.latest_frame_ts_plate = 0.0

    state.lane_sample_window.clear()
    state.lane_boundaries.clear()
    state.lane_boundaries.update(_DEFAULT_BOUNDARIES)
    state.lane_boundaries_revision = 1
    state.lane_boundaries_updated_at_ms = int(time.time() * 1000)

    digital_twin.clear_recording()
    yield
    digital_twin.clear_recording()


@pytest.fixture
def app_client():
    from smart_traffic import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_obfuscated_jpeg():
    img = Image.new("RGB", (32, 24), color=(90, 140, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw = buf.getvalue()

    key = np.resize(np.frombuffer(st_config.XOR_KEY, dtype=np.uint8), len(raw))
    source = np.frombuffer(raw, dtype=np.uint8)
    return np.bitwise_xor(source, key).tobytes()

