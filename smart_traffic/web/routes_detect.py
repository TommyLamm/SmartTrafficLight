from flask import Blueprint, jsonify, request

from ..services.detect_car import process_car_data
from ..services.detect_person import process_legacy_detect_all, process_person_data


bp_detect = Blueprint("detect", __name__)


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
