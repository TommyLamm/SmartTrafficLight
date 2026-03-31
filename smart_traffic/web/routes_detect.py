# smart_traffic/web/routes_detect.py
from flask import Blueprint, Response, jsonify, request

import smart_traffic.state as state

from ..services.detect_car import process_car_data
from ..services.detect_person import process_legacy_detect_all, process_person_data
from ..services.detect_plate import process_plate_data          # ← NEW
from ..services.detect_violation import process_violation_data


bp_detect = Blueprint("detect", __name__)


# ── existing detection routes (unchanged) ─────────────────────────────────────

@bp_detect.route('/capture_violation', methods=['POST'])
def capture_violation():
    try:
        if not request.data:
            return jsonify({"error": "No Data"}), 400
        return jsonify(process_violation_data(request.data)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp_detect.route('/detect_all', methods=['POST'])
def detect_all():
    try:
        if not request.data:
            return jsonify({"error": "No Data"}), 400
        return jsonify(process_legacy_detect_all(request.data)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp_detect.route('/detect_person', methods=['POST'])
def detect_person():
    try:
        if not request.data:
            return jsonify({"error": "No Data"}), 400
        return jsonify(process_person_data(request.data)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp_detect.route('/detect_car', methods=['POST'])
def detect_car():
    try:
        if not request.data:
            return jsonify({"error": "No Data"}), 400
        return jsonify(process_car_data(request.data)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── NEW: licence-plate detection ──────────────────────────────────────────────

@bp_detect.route('/detect_plate', methods=['POST'])
def detect_plate():
    """
    POST  /detect_plate
    Body : XOR-obfuscated JPEG bytes (same encoding as /detect_car).

    Response JSON:
    {
        "plates_this_frame": [
            {"text": "ABC-1234", "confidence": 0.94, "bbox": [x1,y1,x2,y2],
             "timestamp_ms": 1712345678000},
            ...
        ],
        "total_plates": 12,   // cumulative plates in rolling history
        "command": "KEEP"
    }
    """
    try:
        if not request.data:
            return jsonify({"error": "No Data"}), 400
        return jsonify(process_plate_data(request.data)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp_detect.route('/plates')
def plates():
    """
    GET  /plates
    Returns the rolling history of all detected plates stored in sys_state.
    """
    return jsonify({
        "plates": state.sys_state.get("plates", []),
        "count": len(state.sys_state.get("plates", [])),
    })


@bp_detect.route('/stream_plate')
def stream_plate():
    """
    GET  /stream_plate
    MJPEG stream of the plate-annotated frames (mirrors /stream_car pattern).
    """
    def generate():
        while True:
            with state.frame_condition_plate:
                state.frame_condition_plate.wait(timeout=5.0)
                frame = state.latest_frame_plate

            if frame is None:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame +
                b"\r\n"
            )

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
