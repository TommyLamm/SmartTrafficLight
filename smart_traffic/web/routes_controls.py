import os
import re

from flask import Blueprint, jsonify, request, send_from_directory

import smart_traffic.state as state
from smart_traffic.services.control import (
    apply_manual_command,
    clear_emergency,
    tick_emergency_phase,
    trigger_emergency_vehicle,
)

VIOLATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "violations"
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

    raw_lane_counts = state.sys_state.get("lane_counts", [0, 0, 0])
    if not isinstance(raw_lane_counts, (list, tuple)):
        raw_lane_counts = [0, 0, 0]

    lane_counts = []
    for value in list(raw_lane_counts)[:3]:
        try:
            lane_counts.append(int(value))
        except (TypeError, ValueError):
            lane_counts.append(0)
    while len(lane_counts) < 3:
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


def _parse_ratio(payload, key):
    value = payload.get(key)
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
        b1_top = _parse_ratio(payload, "boundary1_top")
        b1_bottom = _parse_ratio(payload, "boundary1_bottom")
        b2_top = _parse_ratio(payload, "boundary2_top")
        b2_bottom = _parse_ratio(payload, "boundary2_bottom")
    except ValueError as e:
        return _json_no_cache({"success": False, "error": str(e)}, status=400)

    if b1_top >= b2_top:
        return _json_no_cache(
            {"success": False, "error": "boundary1_top must be smaller than boundary2_top"},
            status=400,
        )
    if b1_bottom >= b2_bottom:
        return _json_no_cache(
            {"success": False, "error": "boundary1_bottom must be smaller than boundary2_bottom"},
            status=400,
        )

    updated = {
        "boundary1_top": b1_top,
        "boundary1_bottom": b1_bottom,
        "boundary2_top": b2_top,
        "boundary2_bottom": b2_bottom,
    }
    state.set_lane_boundaries(updated)
    return _json_no_cache({"success": True, "lane_boundaries": state.get_lane_boundaries()})


@bp_controls.route('/violation_image/<path:filename>')
def violation_image(filename):
    """Serve a captured violation image by filename."""
    safe_name = os.path.basename(filename)
    return send_from_directory(VIOLATIONS_DIR, safe_name)


@bp_controls.route('/violations')
def violations():
    """Return the list of all violation records."""
    return _json_no_cache({"violations": state.sys_state.get("violations", [])})
