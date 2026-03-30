import os

from flask import Blueprint, jsonify, request, send_from_directory

import smart_traffic.state as state

VIOLATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "violations"
)

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
    def stats():
    data = dict(state.sys_state)
    data["stream_car_online"] = state.is_car_stream_online()
    data["stream_person_online"] = state.is_person_stream_online()
    data["stream_plate_online"] = state.is_plate_stream_online()   # ← NEW
    data["lane_boundaries"] = state.get_lane_boundaries()
    # Avoid sending the full plates history in /stats (use /plates instead)
    data["plates_count"] = len(data.pop("plates", []))             # ← NEW
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
