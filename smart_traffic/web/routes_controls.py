from flask import Blueprint, jsonify, request

import smart_traffic.state as state


bp_controls = Blueprint("controls", __name__)


@bp_controls.route('/stats')
def stats():
    data = dict(state.sys_state)
    data["stream_car_online"] = state.is_car_stream_online()
    data["stream_person_online"] = state.is_person_stream_online()
    return jsonify(data)


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
    return jsonify(state.get_lane_boundaries())


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
        return jsonify({"success": False, "error": str(e)}), 400

    if b1_top >= b2_top:
        return jsonify({"success": False, "error": "boundary1_top must be smaller than boundary2_top"}), 400
    if b1_bottom >= b2_bottom:
        return jsonify({"success": False, "error": "boundary1_bottom must be smaller than boundary2_bottom"}), 400

    updated = {
        "boundary1_top": b1_top,
        "boundary1_bottom": b1_bottom,
        "boundary2_top": b2_top,
        "boundary2_bottom": b2_bottom,
    }
    state.set_lane_boundaries(updated)
    return jsonify({"success": True, "lane_boundaries": state.get_lane_boundaries()})
