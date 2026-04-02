from flask import Blueprint, jsonify, request

from ..services.digital_twin import (
    build_playback,
    clear_recording,
    get_frames,
    get_session,
    run_what_if_compare,
    start_recording,
    stop_recording,
)


bp_digital_twin = Blueprint("digital_twin", __name__)


def _bad_request(message):
    return jsonify({"success": False, "error": str(message)}), 400


@bp_digital_twin.route("/digital_twin/session")
def digital_twin_session():
    return jsonify({"success": True, "session": get_session()})


@bp_digital_twin.route("/digital_twin/start", methods=["POST"])
def digital_twin_start():
    payload = request.get_json(silent=True) or {}
    max_frames = payload.get("max_frames", 900)
    try:
        session = start_recording(max_frames=max_frames)
    except ValueError as exc:
        return _bad_request(exc)
    return jsonify({"success": True, "session": session})


@bp_digital_twin.route("/digital_twin/stop", methods=["POST"])
def digital_twin_stop():
    return jsonify({"success": True, "session": stop_recording()})


@bp_digital_twin.route("/digital_twin/clear", methods=["POST"])
def digital_twin_clear():
    return jsonify({"success": True, "session": clear_recording()})


@bp_digital_twin.route("/digital_twin/frames")
def digital_twin_frames():
    limit = request.args.get("limit", default="200")
    try:
        frames = get_frames(limit=limit)
    except ValueError as exc:
        return _bad_request(exc)
    return jsonify({"success": True, "frames": frames, "count": len(frames)})


@bp_digital_twin.route("/digital_twin/playback")
def digital_twin_playback():
    limit = request.args.get("limit", default="600")
    try:
        playback = build_playback(limit=limit)
    except ValueError as exc:
        return _bad_request(exc)
    return jsonify({"success": True, "playback": playback})


@bp_digital_twin.route("/digital_twin/compare", methods=["POST"])
def digital_twin_compare():
    payload = request.get_json(silent=True) or {}
    strategies = payload.get("strategies")
    try:
        result = run_what_if_compare(strategies=strategies)
    except ValueError as exc:
        return _bad_request(exc)
    return jsonify(result)
