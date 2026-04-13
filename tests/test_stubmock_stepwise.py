import socket
import threading
import time
from http.server import HTTPServer
from pathlib import Path
import sys

import numpy as np
from PIL import Image

import logic
import simulate_car_stream
import smart_traffic.state as state
from smart_traffic.services import control, detect_car, digital_twin

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from stubmock_case_catalog import STUBMOCK_CASES
from stubmock_reporting import assert_case
from test_firmware_contract_replay import _mega_wifi_translation
from test_integration_stream_replay import _ReplayStubHandler, _create_tiny_video


def _case(case_id):
    for item in STUBMOCK_CASES:
        if item["id"] == case_id:
            return item
    raise KeyError(case_id)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def test_stepwise_a1_logic_wheelchair_priority():
    case = _case("A1-logic-wheelchair-priority")
    cmd, light_state = logic.decide_light(
        person_count=1,
        vehicle_count=0,
        wheelchair_count=10,
        current_light_state="CAR_GREEN",
        wheelchair_priority_active=True,
    )
    actual = {"command": cmd, "light_state": light_state}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_a2_emergency_phase_progression():
    case = _case("A2-control-emergency-y2r")
    state.sys_state["emergency_priority_active"] = True
    control.trigger_emergency_vehicle()

    seq = [state.sys_state["command"]]
    state.sys_state["emergency_phase_until"] = 0.0
    control.tick_emergency_phase()
    seq.append(state.sys_state["command"])
    state.sys_state["emergency_phase_until"] = 0.0
    control.tick_emergency_phase()
    seq.append(state.sys_state["command"])
    state.sys_state["emergency_phase_until"] = time.time() - 1.0
    control.tick_emergency_phase()

    actual = {"sequence_prefix": seq[:3], "final_command": state.sys_state["command"]}
    passed = (
        actual["sequence_prefix"] == case["expected"]["sequence_prefix"]
        and actual["final_command"] == case["expected"]["final_command"]
    )
    assert_case(case["id"], case["scenario"], case["expected"], actual, passed)


def test_stepwise_a3_detect_car_lane_counts(monkeypatch):
    case = _case("A3-detect-car-lane-counts")
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
                            [0, 10, 20, 90],
                            [80, 10, 100, 90],
                        ],
                    )
                )
            ]
        ),
    )
    payload = detect_car.process_car_data(b"x")
    actual = {
        "cars_total": payload["cars_total"],
        "lane_counts": payload["lane_counts"],
        "tidal_direction": payload["tidal_direction"],
    }
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_a4_digital_twin_compare(monkeypatch):
    case = _case("A4-digital-twin-compare")
    tick = {"v": 1000}

    def _now_ms():
        tick["v"] += 200
        return tick["v"]

    monkeypatch.setattr(digital_twin, "_now_ms", _now_ms)
    digital_twin.start_recording(max_frames=120)
    for idx in range(20):
        state.sys_state["persons"] = idx % 4
        state.sys_state["cars"] = 3 + (idx % 3)
        state.sys_state["wheelchairs"] = 1 if idx % 5 == 0 else 0
        state.sys_state["lane_counts"] = [idx % 3, 1, (idx + 1) % 3]
        digital_twin.capture_snapshot("car")
    compare = digital_twin.run_what_if_compare(["baseline", "balanced_flow"])
    actual = {"success": compare["success"], "min_strategies": len(compare["strategies"])}
    passed = actual["success"] is True and actual["min_strategies"] >= case["expected"]["min_strategies"]
    assert_case(case["id"], case["scenario"], case["expected"], actual, passed)


def test_stepwise_b1_stats_contract(app_client):
    case = _case("B1-stats-contract")
    state.sys_state["cars"] = 4
    state.sys_state["persons"] = 2
    state.sys_state["wheelchairs"] = 1
    state.sys_state["command"] = "KEEP"
    state.sys_state["lane_counts"] = [1, 2, 1]
    state.sys_state["tidal_direction"] = "BALANCED"
    state.sys_state["plates"] = [{"text": "ABC123"}]

    resp = app_client.get("/stats")
    data = resp.get_json()
    actual = {
        "status_code": resp.status_code,
        "required_keys": [k for k in case["expected"]["required_keys"] if k in data],
        "forbidden_keys": [k for k in case["expected"]["forbidden_keys"] if k in data],
    }
    passed = (
        actual["status_code"] == case["expected"]["status_code"]
        and actual["required_keys"] == case["expected"]["required_keys"]
        and actual["forbidden_keys"] == []
    )
    assert_case(case["id"], case["scenario"], case["expected"], actual, passed)


def test_stepwise_b2_empty_detect_payloads(app_client):
    case = _case("B2-detect-empty-payload")
    statuses = {
        "detect_car": app_client.post("/detect_car", data=b"").status_code,
        "detect_person": app_client.post("/detect_person", data=b"").status_code,
        "detect_plate": app_client.post("/detect_plate", data=b"").status_code,
        "capture_violation": app_client.post("/capture_violation", data=b"").status_code,
    }
    actual = {"status_code": sorted(set(statuses.values())), "raw": statuses}
    passed = all(v == case["expected"]["status_code"] for v in statuses.values())
    assert_case(case["id"], case["scenario"], case["expected"], actual, passed)


def test_stepwise_b3_emergency_routes(app_client):
    case = _case("B3-emergency-route-clear")
    trigger = app_client.post("/trigger_emergency", json={})
    clear = app_client.post("/clear_emergency", json={})
    final_stats = app_client.get("/stats").get_json()
    actual = {
        "trigger_status": trigger.status_code,
        "clear_status": clear.status_code,
        "final_command": final_stats["command"],
    }
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_b4_lane_boundary_validation(app_client):
    case = _case("B4-lane-boundary-validation")
    resp = app_client.post(
        "/lane_boundaries",
        json={
            "boundary1_top": 0.7,
            "boundary1_bottom": 0.3,
            "boundary2_top": 0.6,
            "boundary2_bottom": 0.7,
        },
    )
    actual_json = resp.get_json()
    actual = {"status_code": resp.status_code, "success": bool(actual_json.get("success"))}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_c1_stream_replay_mock(tmp_path, monkeypatch):
    case = _case("C1-stream-replay-mock-http")
    _ReplayStubHandler.detect_car_hits = 0
    _ReplayStubHandler.detect_person_hits = 0

    video_path = Path(tmp_path) / "tiny_replay.avi"
    _create_tiny_video(video_path)

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _ReplayStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    args = [
        "simulate_car_stream.py",
        "--video-path",
        str(video_path),
        "--server-url",
        f"http://127.0.0.1:{port}",
        "--fps",
        "6",
        "--duration-sec",
        "1.2",
        "--resize-width",
        "64",
        "--jpeg-quality",
        "80",
        "--log-interval-sec",
        "0.5",
        "--mirror-to-person",
    ]
    monkeypatch.setattr("sys.argv", args)
    try:
        exit_code = simulate_car_stream.main()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

    actual = {
        "exit_code": exit_code,
        "detect_car_hits_gt": _ReplayStubHandler.detect_car_hits,
        "detect_person_hits_gt": _ReplayStubHandler.detect_person_hits,
    }
    passed = (
        actual["exit_code"] == case["expected"]["exit_code"]
        and actual["detect_car_hits_gt"] > case["expected"]["detect_car_hits_gt"]
        and actual["detect_person_hits_gt"] > case["expected"]["detect_person_hits_gt"]
    )
    assert_case(case["id"], case["scenario"], case["expected"], actual, passed)


def test_stepwise_d1_mega_emergency_clear_translation():
    case = _case("D1-mega-emergency-clear-translation")
    commands = ["EMERGENCY_YELLOW", "EMERGENCY_ALL_RED", "EMERGENCY_RED", "KEEP"]
    translated = _mega_wifi_translation(commands)
    actual = {"translated_suffix": translated[-2:]}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_d2_stats_cars_fallback_key(app_client):
    case = _case("D2-mega-carcount-fallback-contract")
    state.sys_state["cars"] = 11
    data = app_client.get("/stats").get_json()
    actual = {"cars_key_present": "cars" in data}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer E — Newly covered service modules
# ═══════════════════════════════════════════════════════════════════════════════

def test_stepwise_e1_decode_xor_roundtrip():
    import io
    from smart_traffic.config import XOR_KEY
    from smart_traffic.services.decode import decode_image

    case = _case("E1-decode-xor-roundtrip")

    raw_img = Image.new("RGB", (32, 24), color=(90, 140, 200))
    buf = io.BytesIO()
    raw_img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    key = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(raw_bytes))
    obfuscated = np.bitwise_xor(np.frombuffer(raw_bytes, dtype=np.uint8), key).tobytes()

    result = decode_image(obfuscated)
    actual = {"width": result.size[0], "height": result.size[1], "mode": result.mode}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_e2_detect_person_classification():
    from smart_traffic.services.detect_person import classify_person_label

    case = _case("E2-detect-person-classification")
    actual = {
        "person": classify_person_label("person"),
        "peoplewheelchair": classify_person_label("peoplewheelchair"),
        "wheelchair": classify_person_label("wheelchair"),
        "dog": classify_person_label("dog"),
    }
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_e3_detect_person_counting(monkeypatch):
    from smart_traffic.services import detect_person

    case = _case("E3-detect-person-counting")

    class _FakeBoxesP:
        def __init__(self, cls_values):
            self.cls = _FakeTensor(cls_values)

    class _FakeResultP:
        def __init__(self, boxes, names=None):
            self.boxes = boxes
            self.names = names or {}
        def plot(self):
            return np.zeros((48, 64, 3), dtype=np.uint8)

    names = {0: "person", 1: "peopleWheelchair"}
    stub = _FakeResultP(boxes=_FakeBoxesP([0, 0, 1]), names=names)

    monkeypatch.setattr(detect_person, "decode_image", lambda _: Image.new("RGB", (64, 48)))
    monkeypatch.setattr(detect_person, "person_model", _FakeModel([stub]))

    detect_person.process_person_data(b"fake")
    actual = {"persons": state.sys_state["persons"], "wheelchairs": state.sys_state["wheelchairs"]}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_e4_detect_plate_stub_ocr(monkeypatch):
    from smart_traffic.services import detect_plate

    case = _case("E4-detect-plate-stub-ocr")
    state.sys_state["plates"] = []

    class _FakePlateBox:
        def __init__(self, xyxy_values):
            self.xyxy = _FakeTensor([xyxy_values])
    class _FakePlateBoxes:
        def __init__(self, boxes_list):
            self._boxes = [_FakePlateBox(b) for b in boxes_list]
            self.cls = _FakeTensor(list(range(len(boxes_list))))
        def __iter__(self):
            return iter(self._boxes)
        def __len__(self):
            return len(self._boxes)
    class _FakePlateResult:
        def __init__(self, boxes):
            self.boxes = boxes
        def plot(self):
            return np.zeros((48, 64, 3), dtype=np.uint8)
    class _FakeOCR:
        def ocr(self, img):
            return [[[[0, 0, 10, 10], ("TEST999", 0.92)]]]

    monkeypatch.setattr(detect_plate, "decode_image", lambda _: Image.new("RGB", (100, 100)))
    monkeypatch.setattr(detect_plate, "plate_model",
                        _FakeModel([_FakePlateResult(boxes=_FakePlateBoxes([[10, 10, 90, 50]]))]))
    monkeypatch.setattr(detect_plate, "_get_ocr", lambda: _FakeOCR())

    result = detect_plate.process_plate_data(b"fake")
    actual = {"plates_found": len(result["plates_this_frame"]),
              "text": result["plates_this_frame"][0]["text"] if result["plates_this_frame"] else ""}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer F — Arduino Mega firmware stub tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_stepwise_f1_mega_json_parser():
    from test_firmware_mega_stub import parse_json_string, parse_json_long

    case = _case("F1-mega-json-parser")
    actual = {
        "command_compact": parse_json_string('{"command":"CAR_GREEN"}', "command"),
        "command_spaced": parse_json_string('{"command": "PED_GREEN_10"}', "command"),
        "cars_total": parse_json_long('{"cars_total":5}', "cars_total"),
    }
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_f2_mega_brightness_control():
    from test_firmware_mega_stub import brightness_control

    case = _case("F2-mega-brightness-control")
    actual = {
        "high": brightness_control(150),
        "low": brightness_control(0),
        "mid_70": brightness_control(70),
    }
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_f3_mega_fsm_emergency_sequence():
    from test_firmware_mega_stub import MegaFsmStub, STATE_EMERGENCY_YELLOW, STATE_EMERGENCY_ALL_RED, STATE_EMERGENCY_RED_HOLD, STATE_PED_RED_WAIT

    case = _case("F3-mega-fsm-emergency-sequence")
    fsm = MegaFsmStub()

    fsm.process_command("EMERGENCY_YELLOW")
    after_yellow = fsm.current_state
    fsm.process_command("EMERGENCY_ALL_RED")
    after_all_red = fsm.current_state
    fsm.process_command("EMERGENCY_RED")
    after_red = fsm.current_state
    fsm.process_command("EMERGENCY_CLEAR")
    after_clear = fsm.current_state

    _STATE_NAMES = {
        STATE_EMERGENCY_YELLOW: "EMERGENCY_YELLOW",
        STATE_EMERGENCY_ALL_RED: "EMERGENCY_ALL_RED",
        STATE_EMERGENCY_RED_HOLD: "EMERGENCY_RED_HOLD",
        STATE_PED_RED_WAIT: "PED_RED_WAIT",
    }
    actual = {
        "after_yellow": _STATE_NAMES.get(after_yellow, str(after_yellow)),
        "after_all_red": _STATE_NAMES.get(after_all_red, str(after_all_red)),
        "after_red": _STATE_NAMES.get(after_red, str(after_red)),
        "after_clear": _STATE_NAMES.get(after_clear, str(after_clear)),
    }
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_f4_mega_pressure_jam():
    from test_firmware_mega_stub import PressureSensorStub

    case = _case("F4-mega-pressure-jam")
    s = PressureSensorStub()
    s.car_count = 15  # > threshold

    s.read_pressure(70, 0)
    s.read_pressure(70, 61_000_000)

    actual = {"jam": s.jam, "cooling_period": s.cooling_period}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_f5_mega_rfid_uid_match():
    from test_firmware_mega_stub import check_rfid_uid

    case = _case("F5-mega-rfid-uid-match")
    actual = {
        "known_match": check_rfid_uid([0xCC, 0x0E, 0x40, 0x18]),
        "unknown_match": check_rfid_uid([0xDE, 0xAD, 0xBE, 0xEF]),
    }
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer G — Logic edge cases
# ═══════════════════════════════════════════════════════════════════════════════

def test_stepwise_g1_logic_idle_keep():
    case = _case("G1-logic-idle-keep")
    cmd, light_state = logic.decide_light(
        person_count=0, vehicle_count=0, wheelchair_count=0,
        current_light_state="CAR_GREEN",
    )
    actual = {"command": cmd, "light_state": light_state}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


def test_stepwise_g2_logic_wheelchair_disabled():
    case = _case("G2-logic-wheelchair-disabled")
    cmd, light_state = logic.decide_light(
        person_count=1, vehicle_count=0, wheelchair_count=5,
        current_light_state="CAR_GREEN",
        wheelchair_priority_active=False,
    )
    actual = {"not_wheelchair_state": light_state != "PED_WHEELCHAIR"}
    assert_case(case["id"], case["scenario"], case["expected"], actual, actual == case["expected"])


