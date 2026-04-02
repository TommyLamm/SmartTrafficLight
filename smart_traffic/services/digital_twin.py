import threading
import time
from copy import deepcopy

import logic

import smart_traffic.state as state


_CAPTURE_MIN_INTERVAL_MS = 120
_MIN_FRAMES = 60
_MAX_FRAMES = 5000
_DEFAULT_FRAMES = 900

_SESSION_LOCK = threading.Lock()
_recording = False
_started_at_ms = None
_stopped_at_ms = None
_last_capture_at_ms = 0
_max_frames = _DEFAULT_FRAMES
_frames = []


def _now_ms():
    return int(time.time() * 1000)


def _safe_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _coerce_max_frames(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_frames must be an integer") from exc
    if parsed < _MIN_FRAMES or parsed > _MAX_FRAMES:
        raise ValueError(f"max_frames must be between {_MIN_FRAMES} and {_MAX_FRAMES}")
    return parsed


def _normalize_lane_counts(value):
    if isinstance(value, (list, tuple)):
        lane = [_safe_int(v, 0) for v in list(value)[:3]]
    else:
        lane = []
    while len(lane) < 3:
        lane.append(0)
    return lane


def _snapshot_from_state(source, timestamp_ms):
    persons = max(0, _safe_int(state.sys_state.get("persons", 0), 0))
    cars = max(0, _safe_int(state.sys_state.get("cars", 0), 0))
    wheelchairs = max(0, _safe_int(state.sys_state.get("wheelchairs", 0), 0))
    return {
        "timestamp_ms": timestamp_ms,
        "source": str(source),
        "persons": persons,
        "cars": cars,
        "wheelchairs": wheelchairs,
        "lane_counts": _normalize_lane_counts(state.sys_state.get("lane_counts", [])),
        "tidal_direction": str(state.sys_state.get("tidal_direction", "BALANCED")),
        "command_live": str(state.sys_state.get("command", "KEEP")),
        "light_state_live": str(state.sys_state.get("light_state", "UNKNOWN")),
    }


def _session_payload_locked():
    frames_count = len(_frames)
    first_ts = _frames[0]["timestamp_ms"] if frames_count else None
    last_ts = _frames[-1]["timestamp_ms"] if frames_count else None
    return {
        "recording": _recording,
        "started_at_ms": _started_at_ms,
        "stopped_at_ms": _stopped_at_ms,
        "max_frames": _max_frames,
        "frames_count": frames_count,
        "first_frame_ts_ms": first_ts,
        "last_frame_ts_ms": last_ts,
        "duration_ms": (last_ts - first_ts) if frames_count >= 2 else 0,
    }


def _sync_sys_state_locked():
    state.sys_state["digital_twin_recording"] = bool(_recording)
    state.sys_state["digital_twin_frames"] = len(_frames)
    state.sys_state["digital_twin_started_at_ms"] = _started_at_ms
    state.sys_state["digital_twin_last_frame_ts_ms"] = _frames[-1]["timestamp_ms"] if _frames else None


def start_recording(max_frames=_DEFAULT_FRAMES):
    global _recording, _started_at_ms, _stopped_at_ms, _last_capture_at_ms, _max_frames, _frames
    target_max_frames = _coerce_max_frames(max_frames)
    with _SESSION_LOCK:
        _recording = True
        _started_at_ms = _now_ms()
        _stopped_at_ms = None
        _last_capture_at_ms = 0
        _max_frames = target_max_frames
        _frames = []
        _sync_sys_state_locked()
        return _session_payload_locked()


def stop_recording():
    global _recording, _stopped_at_ms
    with _SESSION_LOCK:
        _recording = False
        _stopped_at_ms = _now_ms()
        _sync_sys_state_locked()
        return _session_payload_locked()


def clear_recording():
    global _recording, _started_at_ms, _stopped_at_ms, _last_capture_at_ms, _frames
    with _SESSION_LOCK:
        _recording = False
        _started_at_ms = None
        _stopped_at_ms = None
        _last_capture_at_ms = 0
        _frames = []
        _sync_sys_state_locked()
        return _session_payload_locked()


def get_session():
    with _SESSION_LOCK:
        return _session_payload_locked()


def get_frames(limit=300):
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed_limit < 1 or parsed_limit > _MAX_FRAMES:
        raise ValueError(f"limit must be between 1 and {_MAX_FRAMES}")
    with _SESSION_LOCK:
        return deepcopy(_frames[-parsed_limit:])


def capture_snapshot(source):
    global _last_capture_at_ms
    timestamp_ms = _now_ms()
    with _SESSION_LOCK:
        if not _recording:
            return
        if timestamp_ms - _last_capture_at_ms < _CAPTURE_MIN_INTERVAL_MS:
            return
        _frames.append(_snapshot_from_state(source, timestamp_ms))
        if len(_frames) > _max_frames:
            del _frames[: len(_frames) - _max_frames]
        _last_capture_at_ms = timestamp_ms
        _sync_sys_state_locked()


def build_playback(limit=600):
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed_limit < 1 or parsed_limit > _MAX_FRAMES:
        raise ValueError(f"limit must be between 1 and {_MAX_FRAMES}")

    with _SESSION_LOCK:
        frames = deepcopy(_frames[-parsed_limit:])

    if not frames:
        return {
            "count": 0,
            "duration_ms": 0,
            "points": [],
        }

    first_ts = frames[0]["timestamp_ms"]
    points = []
    for frame in frames:
        points.append({
            "elapsed_ms": max(0, frame["timestamp_ms"] - first_ts),
            "persons": frame["persons"],
            "cars": frame["cars"],
            "wheelchairs": frame["wheelchairs"],
            "lane_counts": frame["lane_counts"],
            "tidal_direction": frame["tidal_direction"],
            "command_live": frame["command_live"],
            "light_state_live": frame["light_state_live"],
            "source": frame["source"],
        })

    return {
        "count": len(points),
        "duration_ms": points[-1]["elapsed_ms"],
        "points": points,
    }


def _baseline_decider(frame, current_state):
    return logic.decide_light(
        frame["persons"],
        frame["cars"],
        frame["wheelchairs"],
        current_state,
    )


def _pedestrian_first_decider(frame, current_state):
    p_count = frame["persons"]
    c_count = frame["cars"]
    w_count = frame["wheelchairs"]

    if w_count > 0:
        if current_state != "PED_WHEELCHAIR":
            return "PED_GREEN_30", "PED_WHEELCHAIR"
        return "KEEP", current_state

    if p_count >= 2:
        if current_state != "PED_LONG":
            return "PED_GREEN_20", "PED_LONG"
        return "KEEP", current_state

    if p_count > 0 and c_count <= 2:
        if current_state != "PED_SHORT":
            return "PED_GREEN_10", "PED_SHORT"
        return "KEEP", current_state

    if c_count > 0 and current_state != "CAR_GREEN":
        return "CAR_GREEN", "CAR_GREEN"

    return "KEEP", current_state


def _vehicle_first_decider(frame, current_state):
    p_count = frame["persons"]
    c_count = frame["cars"]
    w_count = frame["wheelchairs"]

    if c_count >= 2:
        if current_state != "CAR_GREEN":
            return "CAR_GREEN", "CAR_GREEN"
        return "KEEP", current_state

    if w_count > 0 and c_count == 0:
        if current_state != "PED_WHEELCHAIR":
            return "PED_GREEN_30", "PED_WHEELCHAIR"
        return "KEEP", current_state

    if p_count >= 3 and c_count <= 1:
        if current_state != "PED_LONG":
            return "PED_GREEN_20", "PED_LONG"
        return "KEEP", current_state

    if p_count > 0 and c_count == 0 and current_state != "PED_SHORT":
        return "PED_GREEN_10", "PED_SHORT"

    if c_count > 0 and current_state != "CAR_GREEN":
        return "CAR_GREEN", "CAR_GREEN"

    return "KEEP", current_state


def _balanced_flow_decider(frame, current_state):
    p_count = frame["persons"]
    c_count = frame["cars"]
    w_count = frame["wheelchairs"]
    lane_counts = frame["lane_counts"]

    lane_imbalance = abs(lane_counts[0] - lane_counts[-1])
    ped_pressure = p_count + (2 * w_count)
    car_pressure = c_count + (0.5 * lane_imbalance)

    if w_count > 0 and car_pressure <= 2:
        if current_state != "PED_WHEELCHAIR":
            return "PED_GREEN_30", "PED_WHEELCHAIR"
        return "KEEP", current_state

    if ped_pressure > car_pressure + 1.0:
        if p_count >= 3 and current_state != "PED_LONG":
            return "PED_GREEN_20", "PED_LONG"
        if p_count > 0 and current_state != "PED_SHORT":
            return "PED_GREEN_10", "PED_SHORT"
        return "KEEP", current_state

    if car_pressure >= ped_pressure and current_state != "CAR_GREEN":
        return "CAR_GREEN", "CAR_GREEN"

    return "KEEP", current_state


_STRATEGY_DECIDERS = {
    "baseline": _baseline_decider,
    "pedestrian_first": _pedestrian_first_decider,
    "vehicle_first": _vehicle_first_decider,
    "balanced_flow": _balanced_flow_decider,
}


def _simulate_strategy(strategy_name, decider, frames):
    light_state = "UNKNOWN"
    prev_light_state = light_state
    switches = 0
    command_counts = {"KEEP": 0, "CAR_GREEN": 0, "PED_GREEN": 0}
    car_delay_units = 0
    ped_delay_units = 0
    wheelchair_frames = 0
    wheelchair_priority_hits = 0
    timeline = []

    for frame in frames:
        command, light_state = decider(frame, light_state)
        command = str(command or "KEEP")
        light_state = str(light_state or "UNKNOWN")
        if light_state != prev_light_state:
            switches += 1
        prev_light_state = light_state

        if command == "CAR_GREEN":
            command_counts["CAR_GREEN"] += 1
        elif command.startswith("PED_GREEN"):
            command_counts["PED_GREEN"] += 1
        else:
            command_counts["KEEP"] += 1

        car_demand = max(0, frame["cars"])
        ped_demand = max(0, frame["persons"]) + (2 * max(0, frame["wheelchairs"]))

        if command == "CAR_GREEN":
            car_delay_units += max(0, car_demand - 1)
            ped_delay_units += ped_demand
        elif command.startswith("PED_GREEN"):
            car_delay_units += car_demand
            ped_delay_units += max(0, ped_demand - 2)
        else:
            car_delay_units += car_demand
            ped_delay_units += ped_demand

        if frame["wheelchairs"] > 0:
            wheelchair_frames += 1
            if command == "PED_GREEN_30":
                wheelchair_priority_hits += 1

        if len(timeline) < 240:
            timeline.append({
                "timestamp_ms": frame["timestamp_ms"],
                "command": command,
                "light_state": light_state,
            })

    total_delay_units = car_delay_units + ped_delay_units
    if wheelchair_frames:
        wheelchair_rate = round((wheelchair_priority_hits * 100.0) / wheelchair_frames, 2)
    else:
        wheelchair_rate = 50.0

    return {
        "strategy": strategy_name,
        "frames": len(frames),
        "switches": switches,
        "command_counts": command_counts,
        "car_delay_units": car_delay_units,
        "ped_delay_units": ped_delay_units,
        "total_delay_units": total_delay_units,
        "wheelchair_frames": wheelchair_frames,
        "wheelchair_priority_hits": wheelchair_priority_hits,
        "wheelchair_priority_rate": wheelchair_rate,
        "timeline_preview": timeline,
    }


def run_what_if_compare(strategies=None):
    if strategies is None:
        selected = ["baseline", "pedestrian_first", "vehicle_first", "balanced_flow"]
    elif isinstance(strategies, list) and strategies:
        selected = [str(name) for name in strategies]
    else:
        raise ValueError("strategies must be a non-empty list")

    unknown = [name for name in selected if name not in _STRATEGY_DECIDERS]
    if unknown:
        raise ValueError(f"Unknown strategy names: {', '.join(unknown)}")

    with _SESSION_LOCK:
        frames = deepcopy(_frames)

    if len(frames) < 15:
        raise ValueError("Need at least 15 recorded frames before running what-if compare")

    results = []
    for name in selected:
        result = _simulate_strategy(name, _STRATEGY_DECIDERS[name], frames)
        results.append(result)

    min_delay = min(r["total_delay_units"] for r in results)
    max_delay = max(r["total_delay_units"] for r in results)
    max_switches = max(r["switches"] for r in results)

    for result in results:
        if max_delay == min_delay:
            delay_score = 100.0
        else:
            delay_score = 100.0 * (max_delay - result["total_delay_units"]) / (max_delay - min_delay)

        if max_switches == 0:
            stability_score = 100.0
        else:
            stability_score = 100.0 * (max_switches - result["switches"]) / max_switches

        wheelchair_score = result["wheelchair_priority_rate"]
        demo_score = (0.55 * delay_score) + (0.25 * wheelchair_score) + (0.20 * stability_score)

        result["delay_score"] = round(delay_score, 2)
        result["stability_score"] = round(stability_score, 2)
        result["demo_score"] = round(demo_score, 2)

    ranked = sorted(results, key=lambda item: item["demo_score"], reverse=True)
    winner = ranked[0]["strategy"]

    return {
        "success": True,
        "winner": winner,
        "frames_used": len(frames),
        "strategies": ranked,
    }
