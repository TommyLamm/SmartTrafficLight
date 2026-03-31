import io
import os
import time

import cv2
import numpy as np
from PIL import Image

from ..config import XOR_KEY
from ..models import car_model          # reuse existing YOLO — swap for plate model later
from ..services.decode import decode_image
from ..state import sys_state


def process_violation_data(obfuscated_bytes):
    """
    Called by /capture_violation endpoint.
    Decodes the HD frame from ESP32, runs detection,
    saves the image to disk, and logs the event in sys_state.
    """
    image = decode_image(obfuscated_bytes)

    # Run detection on HD frame (reuse car model until plate model is ready)
    results = car_model.predict(
        source=image,
        imgsz=1280,          # full HD resolution
        classes=[2, 3, 5, 7],
        save=False,
        conf=0.30,
        agnostic_nms=True,
    )

    detected_count = sum(
        int(len(r.boxes.cls)) for r in results if r.boxes is not None
    )

    # Save annotated violation image to disk
    timestamp = int(time.time() * 1000)
    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "violations")
    os.makedirs(save_dir, exist_ok=True)

    annotated = results[0].plot()
    filename = f"violation_{timestamp}.jpg"
    filepath = os.path.join(save_dir, filename)
    cv2.imwrite(filepath, annotated)

    # Log into sys_state so /stats and the UI can see it
    record = {
        "timestamp": timestamp,
        "filename": filename,
        "vehicles_detected": detected_count,
    }
    sys_state["violations"].append(record)

    return {
        "success": True,
        "timestamp": timestamp,
        "filename": filename,
        "vehicles_detected": detected_count,
        "total_violations": len(sys_state["violations"]),
    }
