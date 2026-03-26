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
