"""Tests for smart_traffic.services.detect_plate — plate detection + OCR stub."""

import numpy as np
from PIL import Image

import smart_traffic.state as state
from smart_traffic.services import detect_plate


# ── Stub classes ─────────────────────────────────────────────────────────────

class _FakeTensor:
    def __init__(self, data):
        self._data = np.asarray(data, dtype=float)

    def cpu(self):
        return self

    def numpy(self):
        return self._data

    def __len__(self):
        return len(self._data)

    def __getitem__(self, idx):
        return _FakeTensor(self._data[idx])


class _FakeBox:
    """Represents a single detection box."""
    def __init__(self, xyxy_values):
        self.xyxy = _FakeTensor([xyxy_values])


class _FakeBoxes:
    def __init__(self, boxes_list):
        self._boxes = [_FakeBox(b) for b in boxes_list]
        self.cls = _FakeTensor(list(range(len(boxes_list))))

    def __iter__(self):
        return iter(self._boxes)

    def __len__(self):
        return len(self._boxes)


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


class _FakeOCR:
    """Stub PaddleOCR that returns a fixed plate text."""
    def __init__(self, text="ABC1234", conf=0.95):
        self._text = text
        self._conf = conf

    def ocr(self, img):
        # Legacy PaddleOCR format: [ [ [box_coords, (text, score)] ] ]
        return [[[[0, 0, 10, 10], (self._text, self._conf)]]]


# ══════════════════════════════════════════════════════════════════════════════
#  process_plate_data — detection disabled
# ══════════════════════════════════════════════════════════════════════════════

def test_process_plate_data_detection_disabled():
    """When detection is off, return empty plates_this_frame."""
    state.sys_state["detection"] = False
    state.sys_state["plates"] = [{"text": "OLD1"}]

    result = detect_plate.process_plate_data(b"ignored")

    assert result["plates_this_frame"] == []
    assert result["total_plates"] == 1  # existing history preserved
    assert "command" in result


# ══════════════════════════════════════════════════════════════════════════════
#  process_plate_data — with stubbed model + OCR
# ══════════════════════════════════════════════════════════════════════════════

def test_process_plate_data_detects_and_ocr_plates(monkeypatch):
    """Stub model detects 1 plate box, stub OCR reads 'TEST999'."""
    state.sys_state["plates"] = []

    # Stub decode_image
    monkeypatch.setattr(detect_plate, "decode_image",
                        lambda _: Image.new("RGB", (100, 100)))

    # Stub plate model: 1 detection box
    stub_result = _FakeResult(
        boxes=_FakeBoxes([[10, 10, 90, 50]])
    )
    monkeypatch.setattr(detect_plate, "plate_model", _FakeModel([stub_result]))

    # Stub OCR
    monkeypatch.setattr(detect_plate, "_get_ocr", lambda: _FakeOCR("TEST999", 0.92))

    result = detect_plate.process_plate_data(b"fake-obfuscated")

    assert len(result["plates_this_frame"]) == 1
    assert result["plates_this_frame"][0]["text"] == "TEST999"
    assert result["plates_this_frame"][0]["confidence"] == 0.92
    assert result["total_plates"] == 1
    assert len(state.sys_state["plates"]) == 1


def test_process_plate_data_no_detections(monkeypatch):
    """Model finds zero plates → plates_this_frame is empty."""
    state.sys_state["plates"] = []

    monkeypatch.setattr(detect_plate, "decode_image",
                        lambda _: Image.new("RGB", (100, 100)))

    stub_result = _FakeResult(boxes=None)
    monkeypatch.setattr(detect_plate, "plate_model", _FakeModel([stub_result]))
    # _get_ocr() is called before boxes check in source; must stub it
    monkeypatch.setattr(detect_plate, "_get_ocr", lambda: _FakeOCR())

    result = detect_plate.process_plate_data(b"fake")

    assert result["plates_this_frame"] == []
    assert result["total_plates"] == 0


def test_process_plate_data_caps_history_at_maxlen(monkeypatch):
    """Plate history should not exceed PLATE_HISTORY_MAXLEN."""
    from smart_traffic.config import PLATE_HISTORY_MAXLEN

    # Pre-fill history to capacity
    state.sys_state["plates"] = [{"text": f"OLD{i}"} for i in range(PLATE_HISTORY_MAXLEN)]
    assert len(state.sys_state["plates"]) == PLATE_HISTORY_MAXLEN

    monkeypatch.setattr(detect_plate, "decode_image",
                        lambda _: Image.new("RGB", (100, 100)))

    stub_result = _FakeResult(
        boxes=_FakeBoxes([[10, 10, 90, 50]])
    )
    monkeypatch.setattr(detect_plate, "plate_model", _FakeModel([stub_result]))
    monkeypatch.setattr(detect_plate, "_get_ocr", lambda: _FakeOCR("NEW001", 0.80))

    result = detect_plate.process_plate_data(b"fake")

    # Should still be at max capacity, old records popped
    assert len(state.sys_state["plates"]) == PLATE_HISTORY_MAXLEN
    assert state.sys_state["plates"][-1]["text"] == "NEW001"
    # Oldest record should have been evicted
    assert state.sys_state["plates"][0]["text"] != "OLD0"
