# smart_traffic/state.py  (diff: added plate stream fields + "plates" in sys_state)
import hashlib
import json
import os
import tempfile
import threading
import time
from collections import deque

from .config import (
    CAR_LANE_REGION_COUNT,
    LANE_BOUNDARY1_BOTTOM_RATIO,
    LANE_BOUNDARY1_TOP_RATIO,
    LANE_BOUNDARY2_BOTTOM_RATIO,
    LANE_BOUNDARY2_TOP_RATIO,
    STREAM_ONLINE_TTL_SEC,
    TIDAL_SAMPLE_WINDOW,
)


# ── live JPEG frame buffers ───────────────────────────────────────────────────
latest_frame = None
latest_frame_person = None
latest_frame_car = None
latest_frame_plate = None                         # ← NEW: plate-annotated frames

latest_frame_ts_person = 0.0
latest_frame_ts_car = 0.0
latest_frame_ts_plate = 0.0                       # ← NEW

frame_condition = threading.Condition()           # backward-compatible alias (person)
frame_condition_person = frame_condition
frame_condition_car = threading.Condition()
frame_condition_plate = threading.Condition()     # ← NEW
infer_lock = threading.Lock()

# ── shared application state ──────────────────────────────────────────────────
sys_state = {
    "persons": 0,
    "cars": 0,
    "wheelchairs": 0,
    "command": "KEEP",
    "light_state": "UNKNOWN",
    "mode": "AUTO",
    "manual_override": None,
    "last_manual_label": None,
    "detection": True,
    "lane_counts": [0] * CAR_LANE_REGION_COUNT,
    "tidal_direction": "BALANCED",
    "violations": [],
    "plates": [],                                  # ← NEW: rolling OCR history
}

# ── lane-boundary state (unchanged from original) ────────────────────────────
lane_sample_window = deque(maxlen=TIDAL_SAMPLE_WINDOW)
lane_boundary_lock = threading.Lock()
lane_boundaries = {
    "boundary1_top": float(LANE_BOUNDARY1_TOP_RATIO),
    "boundary1_bottom": float(LANE_BOUNDARY1_BOTTOM_RATIO),
    "boundary2_top": float(LANE_BOUNDARY2_TOP_RATIO),
    "boundary2_bottom": float(LANE_BOUNDARY2_BOTTOM_RATIO),
}
lane_boundaries_revision = 1
lane_boundaries_updated_at_ms = int(time.time() * 1000)
_lane_boundary_path_seed = os.path.abspath(os.path.dirname(__file__)).encode("utf-8")
_lane_boundary_path_hash = hashlib.sha1(_lane_boundary_path_seed).hexdigest()[:12]
lane_boundaries_state_path = os.path.join(
    tempfile.gettempdir(),
    f"smart_traffic_lane_boundaries_{_lane_boundary_path_hash}.json",
)
lane_boundaries_state_mtime_ns = 0


# ── stream-online helpers ─────────────────────────────────────────────────────
def is_stream_online(last_frame_ts, ttl_sec=STREAM_ONLINE_TTL_SEC):
    if last_frame_ts <= 0:
        return False
    return (time.time() - last_frame_ts) <= ttl_sec


def is_person_stream_online(ttl_sec=STREAM_ONLINE_TTL_SEC):
    return is_stream_online(latest_frame_ts_person, ttl_sec)


def is_car_stream_online(ttl_sec=STREAM_ONLINE_TTL_SEC):
    return is_stream_online(latest_frame_ts_car, ttl_sec)


def is_plate_stream_online(ttl_sec=STREAM_ONLINE_TTL_SEC):     # ← NEW
    return is_stream_online(latest_frame_ts_plate, ttl_sec)


# ── lane-boundary helpers (identical to original) ────────────────────────────
def _validate_boundary_payload(payload):
    keys = ("boundary1_top", "boundary1_bottom", "boundary2_top", "boundary2_bottom")
    parsed = {}
    for key in keys:
        if key not in payload:
            raise ValueError(f"Missing lane boundary key: {key}")
        try:
            value = float(payload[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid lane boundary value for {key}") from exc
        if value < 0.0 or value > 1.0:
            raise ValueError(f"Lane boundary value out of range for {key}")
        parsed[key] = value

    if parsed["boundary1_top"] >= parsed["boundary2_top"]:
        raise ValueError("boundary1_top must be smaller than boundary2_top")
    if parsed["boundary1_bottom"] >= parsed["boundary2_bottom"]:
        raise ValueError("boundary1_bottom must be smaller than boundary2_bottom")

    try:
        revision = int(payload.get("revision", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid lane boundary revision") from exc
    if revision < 1:
        raise ValueError("Lane boundary revision must be >= 1")

    try:
        updated_at_ms = int(payload.get("updated_at_ms", int(time.time() * 1000)))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid lane boundary updated_at_ms") from exc
    if updated_at_ms < 0:
        raise ValueError("lane boundary updated_at_ms must be >= 0")

    return {**parsed, "revision": revision, "updated_at_ms": updated_at_ms}


def _read_lane_boundaries_from_disk():
    with open(lane_boundaries_state_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return _validate_boundary_payload(payload)


def _write_lane_boundaries_to_disk_locked():
    global lane_boundaries_state_mtime_ns
    payload = {
        **lane_boundaries,
        "revision": lane_boundaries_revision,
        "updated_at_ms": lane_boundaries_updated_at_ms,
    }
    tmp_path = f"{lane_boundaries_state_path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True, separators=(",", ":"))
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.replace(tmp_path, lane_boundaries_state_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    lane_boundaries_state_mtime_ns = os.stat(lane_boundaries_state_path).st_mtime_ns


def _refresh_lane_boundaries_from_disk_locked():
    global lane_boundaries_revision, lane_boundaries_updated_at_ms, lane_boundaries_state_mtime_ns
    try:
        disk_stat = os.stat(lane_boundaries_state_path)
    except FileNotFoundError:
        return
    if disk_stat.st_mtime_ns <= lane_boundaries_state_mtime_ns:
        return
    try:
        disk_payload = _read_lane_boundaries_from_disk()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        lane_boundaries_state_mtime_ns = disk_stat.st_mtime_ns
        print(f"[lane_boundaries] invalid persisted state ignored: {exc}")
        return
    lane_boundaries_state_mtime_ns = disk_stat.st_mtime_ns
    is_newer = (
        disk_payload["revision"] > lane_boundaries_revision
        or (
            disk_payload["revision"] == lane_boundaries_revision
            and disk_payload["updated_at_ms"] > lane_boundaries_updated_at_ms
        )
    )
    if not is_newer:
        return
    lane_boundaries.update({k: disk_payload[k] for k in
                             ("boundary1_top", "boundary1_bottom",
                              "boundary2_top", "boundary2_bottom")})
    lane_boundaries_revision = disk_payload["revision"]
    lane_boundaries_updated_at_ms = disk_payload["updated_at_ms"]


def get_lane_boundaries():
    with lane_boundary_lock:
        _refresh_lane_boundaries_from_disk_locked()
        return {
            **lane_boundaries,
            "revision": lane_boundaries_revision,
            "updated_at_ms": lane_boundaries_updated_at_ms,
        }


def set_lane_boundaries(new_values):
    global lane_boundaries_revision, lane_boundaries_updated_at_ms
    with lane_boundary_lock:
        _refresh_lane_boundaries_from_disk_locked()
        lane_boundaries.update(new_values)
        lane_boundaries_revision += 1
        current_ms = int(time.time() * 1000)
        lane_boundaries_updated_at_ms = max(current_ms, lane_boundaries_updated_at_ms + 1)
        _write_lane_boundaries_to_disk_locked()
