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
from ..models import plate_model
from paddleocr import PaddleOCR
import threading

_ocr_lock = threading.Lock()
_ocr = None

def _get_ocr():
    global _ocr
    if _ocr is None:
        with _ocr_lock:
            if _ocr is None:
                _ocr = PaddleOCR(use_angle_cls=True, lang="en")
    return _ocr

def process_violation_data(obfuscated_bytes):
    """
    Called by /capture_violation endpoint.
    Decodes the HD frame from ESP32, runs detection,
    saves the image to disk, and logs the event in sys_state.
    """
    image = decode_image(obfuscated_bytes)
    # Run plate model on the same frame
    plate_results = plate_model.predict(
        source=image, imgsz=640, conf=0.25, save=False
    )

    plate_text, plate_conf = "N/A", 0.0
    if plate_results[0].boxes is not None:
        frame_bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        img_h, img_w = frame_bgr.shape[:2]
        ocr = _get_ocr()
        for box in plate_results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(img_w, x2), min(img_h, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = frame_bgr[y1:y2, x1:x2]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            crop_up = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            crop_up = cv2.cvtColor(crop_up, cv2.COLOR_GRAY2BGR)
            result = ocr.ocr(crop_up)
            if result and result[0]:
                inner = result[0][0]
                if inner and len(inner) >= 2:
                    plate_text = str(inner[1][0])
                    plate_conf = round(float(inner[1][1]), 3)
                    break  # take the first/best plate
    
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
        "plate_text": plate_text,        # ← ADD
        "plate_confidence": plate_conf,  # ← ADD
    }
    sys_state["violations"].append(record)

    return {
        "success": True,
        "timestamp": timestamp,
        "filename": filename,
        "vehicles_detected": detected_count,
        "total_violations": len(sys_state["violations"]),
        "plate_text": plate_text,        # ← ADD
        "plate_confidence": plate_conf,  # ← ADD
    }
