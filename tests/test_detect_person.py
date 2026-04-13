"""Tests for smart_traffic.services.detect_person — label classification + process pipeline."""

import numpy as np
from PIL import Image

import smart_traffic.state as state
from smart_traffic.services import detect_person
from smart_traffic.services.detect_person import (
    class_name,
    classify_person_label,
    normalize_label,
)


# ── Stub classes for YOLO model ──────────────────────────────────────────────

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
    def __init__(self, cls_values):
        self.cls = _FakeTensor(cls_values)


class _FakeResult:
    def __init__(self, boxes, names=None):
        self.boxes = boxes
        self.names = names or {}

    def plot(self):
        return np.zeros((48, 64, 3), dtype=np.uint8)


class _FakeModel:
    def __init__(self, results):
        self._results = results

    def predict(self, **kwargs):
        return self._results


# ══════════════════════════════════════════════════════════════════════════════
#  normalize_label
# ══════════════════════════════════════════════════════════════════════════════

def test_normalize_label_lowercases_and_strips_non_alnum():
    assert normalize_label("Person") == "person"
    assert normalize_label("People_Wheelchair") == "peoplewheelchair"
    assert normalize_label("PERSON-IN-WHEELCHAIR") == "personinwheelchair"
    assert normalize_label("  W h e e l c h a i r  ") == "wheelchair"


def test_normalize_label_handles_numeric_input():
    assert normalize_label(42) == "42"
    assert normalize_label(0) == "0"


# ══════════════════════════════════════════════════════════════════════════════
#  class_name
# ══════════════════════════════════════════════════════════════════════════════

def test_class_name_dict_mapping():
    names = {0: "person", 1: "peopleWheelchair", 2: "wheelchair"}
    assert class_name(names, 0) == "person"
    assert class_name(names, 1) == "peopleWheelchair"
    assert class_name(names, 99) == "99"  # fallback for unknown


def test_class_name_list_mapping():
    names = ["person", "peopleWheelchair", "wheelchair"]
    assert class_name(names, 0) == "person"
    assert class_name(names, 2) == "wheelchair"
    assert class_name(names, 10) == "10"  # out of range → str(cls_id)


# ══════════════════════════════════════════════════════════════════════════════
#  classify_person_label
# ══════════════════════════════════════════════════════════════════════════════

def test_classify_person_label_all_categories():
    assert classify_person_label("person") == "person"
    assert classify_person_label("peoplewheelchair") == "people_wheelchair"
    assert classify_person_label("personwheelchair") == "people_wheelchair"
    assert classify_person_label("peopleinwheelchair") == "people_wheelchair"
    assert classify_person_label("personinwheelchair") == "people_wheelchair"
    assert classify_person_label("wheelchair") == "wheelchair"
    assert classify_person_label("dog") == "ignore"
    assert classify_person_label("car") == "ignore"


# ══════════════════════════════════════════════════════════════════════════════
#  process_person_data — Stubbed YOLO model
# ══════════════════════════════════════════════════════════════════════════════

def test_process_person_data_detection_disabled():
    """When detection is off, just return current state snapshot."""
    state.sys_state["detection"] = False
    state.sys_state["persons"] = 5
    state.sys_state["wheelchairs"] = 2
    state.sys_state["cars"] = 3

    result = detect_person.process_person_data(b"ignored")

    assert result["persons"] == 5
    assert result["wheelchairs"] == 2
    assert result["cars"] == 3
    assert result["command"] == "KEEP"


def test_process_person_data_counts_persons_and_wheelchairs(monkeypatch):
    """Stub model returns 2 persons + 1 person-in-wheelchair → p=3, w=1."""
    names = {0: "person", 1: "peopleWheelchair"}
    stub_result = _FakeResult(
        boxes=_FakeBoxes(cls_values=[0, 0, 1]),  # 2 persons + 1 peopleWheelchair
        names=names,
    )
    monkeypatch.setattr(detect_person, "decode_image", lambda _: Image.new("RGB", (64, 48)))
    monkeypatch.setattr(detect_person, "person_model", _FakeModel([stub_result]))

    result = detect_person.process_person_data(b"fake-obfuscated")

    assert state.sys_state["persons"] == 3   # 2 person + 1 peopleWheelchair
    assert state.sys_state["wheelchairs"] == 1
    assert result["persons"] == 3
    assert result["wheelchairs"] == 1


def test_process_person_data_zero_detections(monkeypatch):
    """No detections → persons=0, wheelchairs=0."""
    stub_result = _FakeResult(boxes=_FakeBoxes(cls_values=[]), names={})
    monkeypatch.setattr(detect_person, "decode_image", lambda _: Image.new("RGB", (64, 48)))
    monkeypatch.setattr(detect_person, "person_model", _FakeModel([stub_result]))

    result = detect_person.process_person_data(b"fake")

    assert result["persons"] == 0
    assert result["wheelchairs"] == 0


def test_process_person_data_ignores_wheelchair_only_labels(monkeypatch):
    """V2 model: standalone 'wheelchair' (empty) → not counted as person or wheelchair."""
    names = {0: "person", 2: "wheelchair"}
    stub_result = _FakeResult(
        boxes=_FakeBoxes(cls_values=[0, 2]),  # 1 person + 1 empty wheelchair
        names=names,
    )
    monkeypatch.setattr(detect_person, "decode_image", lambda _: Image.new("RGB", (64, 48)))
    monkeypatch.setattr(detect_person, "person_model", _FakeModel([stub_result]))

    result = detect_person.process_person_data(b"fake")

    assert result["persons"] == 1      # only the person
    assert result["wheelchairs"] == 0  # empty wheelchair not counted
