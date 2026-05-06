import os
import re

from flask import Blueprint, jsonify, request, send_from_directory

import smart_traffic.state as state
from smart_traffic.config import CAR_LANE_REGION_COUNT
from smart_traffic.services.control import (
    apply_manual_command,
    clear_emergency,
    tick_emergency_phase,
    trigger_emergency_vehicle,
)


bp_controls = Blueprint("controls", __name__)
_PED_GREEN_CMD_RE = re.compile(r"^PED_GREEN_(\d+)$")


def _json_no_cache(payload, status=200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _build_mega_stats_payload():
    command = str(state.sys_state.get("command", "KEEP") or "KEEP")

    try:
        cars_total = int(state.sys_state.get("cars", 0))
    except (TypeError, ValueError):
        cars_total = 0

    raw_lane_counts = state.sys_state.get("lane_counts", [0] * CAR_LANE_REGION_COUNT)
    if not isinstance(raw_lane_counts, (list, tuple)):
        raw_lane_counts = [0] * CAR_LANE_REGION_COUNT

    lane_counts = []
    for value in list(raw_lane_counts)[:CAR_LANE_REGION_COUNT]:
        try:
            lane_counts.append(int(value))
        except (TypeError, ValueError):
            lane_counts.append(0)
    while len(lane_counts) < CAR_LANE_REGION_COUNT:
        lane_counts.append(0)

    tidal_direction = str(state.sys_state.get("tidal_direction", "BALANCED") or "BALANCED")

    try:
        sample_window = int(len(state.lane_sample_window))
    except (TypeError, ValueError):
        sample_window = 0

    mode = str(state.sys_state.get("mode", "AUTO") or "AUTO").upper()
    if mode not in ("AUTO", "MANUAL"):
        mode = "AUTO"

    emergency_priority_active = bool(state.sys_state.get("emergency_priority_active", True))

    return {
        "command": command,
        "cars_total": cars_total,
        "lane_counts": lane_counts,
        "tidal_direction": tidal_direction,
        "sample_window": sample_window,
        "mode": mode,
        "emergency_priority_active": emergency_priority_active,
    }


@bp_controls.route('/stats')
def stats():
    tick_emergency_phase()

    # Keep default /stats payload unchanged for UI; use ?client=mega for compact MCU payload.
    client = str(request.args.get("client", "")).strip().lower()
    if client == "mega":
        return _json_no_cache(_build_mega_stats_payload())

    data = dict(state.sys_state)
    # Mega polls /stats directly; keep key names aligned with legacy ESP32 parsing.
    data["command"] = str(data.get("command", "KEEP"))
    data["cars_total"] = int(data.get("cars", 0))
    data["sample_window"] = len(state.lane_sample_window)
    data["stream_car_online"] = state.is_car_stream_online()
    data["stream_person_online"] = state.is_person_stream_online()
    data["stream_plate_online"] = state.is_plate_stream_online()   # ← NEW
    data["lane_boundaries"] = state.get_lane_boundaries()
    data["digital_twin_recording"] = bool(state.sys_state.get("digital_twin_recording", False))
    data["digital_twin_frames"] = int(state.sys_state.get("digital_twin_frames", 0))
    # Avoid sending the full plates history in /stats (use /plates instead)
    data["plates_count"] = len(data.pop("plates", []))             # ← NEW
    return _json_no_cache(data)


@bp_controls.route('/set_mode', methods=['POST'])
def set_mode():
    payload = request.json or {}
    mode = payload.get("mode")
    if mode in ["AUTO", "MANUAL"]:
        state.sys_state["mode"] = mode
        if mode == "AUTO":
            state.sys_state["manual_override"] = None
            state.sys_state["manual_command"] = None
            state.sys_state["last_manual_label"] = None
            state.sys_state["command"] = "KEEP"
        else:
            state.sys_state["manual_override"] = None
            state.sys_state["manual_command"] = None
            state.sys_state["command"] = "KEEP"
    return jsonify({"success": True, "mode": state.sys_state["mode"]})


def _is_valid_manual_command(command):
    if command == "CAR_GREEN":
        return True
    if not isinstance(command, str):
        return False
    match = _PED_GREEN_CMD_RE.fullmatch(command.strip())
    if not match:
        return False
    seconds = int(match.group(1))
    return 5 <= seconds <= 120


@bp_controls.route('/manual_override', methods=['POST'])
def manual_override():
    if state.sys_state["mode"] != "MANUAL":
        return _json_no_cache(
            {"success": False, "error": "Switch to MANUAL mode before overriding"},
            status=400,
        )

    payload = request.json or {}
    command = payload.get("command")
    if not _is_valid_manual_command(command):
        return _json_no_cache({"success": False, "error": "Invalid manual command"}, status=400)

    apply_manual_command(command)
    return _json_no_cache(
        {
            "success": True,
            "command": state.sys_state["command"],
            "last_manual_label": state.sys_state["last_manual_label"],
        }
    )


@bp_controls.route('/toggle_detection', methods=['POST'])
def toggle_detection():
    state.sys_state["detection"] = not state.sys_state["detection"]
    return jsonify({"success": True, "detection": state.sys_state["detection"]})


@bp_controls.route('/toggle_emergency', methods=['POST'])
def toggle_emergency():
    state.sys_state["emergency_priority_active"] = not state.sys_state["emergency_priority_active"]
    active = state.sys_state["emergency_priority_active"]
    if not active:
        clear_emergency()
    return jsonify({"success": True, "emergency_priority_active": active})


@bp_controls.route('/toggle_wheelchair_priority', methods=['POST'])
def toggle_wheelchair_priority():
    state.sys_state["wheelchair_priority_active"] = not state.sys_state["wheelchair_priority_active"]
    return jsonify({
        "success": True,
        "wheelchair_priority_active": state.sys_state["wheelchair_priority_active"],
    })


@bp_controls.route('/trigger_emergency', methods=['POST'])
def trigger_emergency_route():
    trigger_emergency_vehicle()
    return jsonify({
        "success": True,
        "phase": state.sys_state["emergency_phase"],
        "light_state": state.sys_state["light_state"],
    })


@bp_controls.route('/clear_emergency', methods=['POST'])
def clear_emergency_route():
    clear_emergency()
    return jsonify({"success": True})


@bp_controls.route('/lane_boundaries')
def lane_boundaries():
    return _json_no_cache(state.get_lane_boundaries())


def _parse_ratio(payload, key, fallback_keys=()):
    value = payload.get(key)
    if value is None:
        for fallback_key in fallback_keys:
            value = payload.get(fallback_key)
            if value is not None:
                break
    if value is None:
        raise ValueError(f"Missing field: {key}")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid number for {key}")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{key} must be between 0 and 1")
    return value


@bp_controls.route('/lane_boundaries', methods=['POST'])
def set_lane_boundaries():
    payload = request.json or {}
    try:
        boundary_top = _parse_ratio(payload, "boundary_top", fallback_keys=("boundary1_top",))
        boundary_bottom = _parse_ratio(payload, "boundary_bottom", fallback_keys=("boundary1_bottom",))
    except ValueError as e:
        return _json_no_cache({"success": False, "error": str(e)}, status=400)

    updated = {
        "boundary_top": boundary_top,
        "boundary_bottom": boundary_bottom,
    }
    state.set_lane_boundaries(updated)
    return _json_no_cache({"success": True, "lane_boundaries": state.get_lane_boundaries()})
