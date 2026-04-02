from flask import Blueprint, jsonify, request

import smart_traffic.state as state
from smart_traffic.services.control import clear_emergency, trigger_emergency_vehicle


bp_controls = Blueprint("controls", __name__)


def _json_no_cache(payload, status=200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp_controls.route('/stats')
def stats():
    data = dict(state.sys_state)
    data["stream_car_online"] = state.is_car_stream_online()
    data["stream_person_online"] = state.is_person_stream_online()
    data["lane_boundaries"] = state.get_lane_boundaries()
    return _json_no_cache(data)


@bp_controls.route('/set_mode', methods=['POST'])
def set_mode():
    mode = request.json.get("mode")
    if mode in ["AUTO", "MANUAL"]:
        state.sys_state["mode"] = mode
    return jsonify({"success": True, "mode": state.sys_state["mode"]})


@bp_controls.route('/manual_override', methods=['POST'])
def manual_override():
    if state.sys_state["mode"] == "MANUAL":
        state.sys_state["manual_override"] = request.json.get("command")
    return jsonify({"success": True})


@bp_controls.route('/toggle_detection', methods=['POST'])
def toggle_detection():
    state.sys_state["detection"] = not state.sys_state["detection"]
    return jsonify({"success": True, "detection": state.sys_state["detection"]})


# ── Feature Toggle: Emergency Vehicle Priority ────────────────────────────
@bp_controls.route('/toggle_emergency', methods=['POST'])
def toggle_emergency():
    """
    Toggle the emergency vehicle RFID priority feature on/off.
    If turned off while an emergency is active, the emergency is also cleared.
    """
    state.sys_state["emergency_priority_active"] = not state.sys_state["emergency_priority_active"]
    active = state.sys_state["emergency_priority_active"]
    if not active:
        clear_emergency()
    return jsonify({"success": True, "emergency_priority_active": active})


# ── Feature Toggle: Wheelchair Adaptive Green Time ────────────────────────
@bp_controls.route('/toggle_wheelchair_priority', methods=['POST'])
def toggle_wheelchair_priority():
    """Toggle the adaptive wheelchair green time feature on/off."""
    state.sys_state["wheelchair_priority_active"] = not state.sys_state["wheelchair_priority_active"]
    active = state.sys_state["wheelchair_priority_active"]
    return jsonify({"success": True, "wheelchair_priority_active": active})


# ── Emergency Vehicle RFID Trigger ────────────────────────────────────────
@bp_controls.route('/trigger_emergency', methods=['POST'])
def trigger_emergency_route():
    """
    Called by the RFID reader (or for manual testing) to start the
    3-phase emergency vehicle priority sequence.
    """
    trigger_emergency_vehicle()
    return jsonify({"success": True, "phase": state.sys_state["emergency_phase"]})


@bp_controls.route('/clear_emergency', methods=['POST'])
def clear_emergency_route():
    """Manually clear an active emergency and return to normal AUTO logic."""
    clear_emergency()
    return jsonify({"success": True})


# ── Lane Boundaries (unchanged from original) ─────────────────────────────
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
        b1_top    = _parse_ratio(payload, "boundary1_top")
        b1_bottom = _parse_ratio(payload, "boundary1_bottom")
        b2_top    = _parse_ratio(payload, "boundary2_top")
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