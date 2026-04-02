# smart_traffic/services/detect_plate.py
# ─────────────────────────────────────────────────────────────────────────────
# Licence-plate detection + OCR service.
#
# Pipeline per frame:
#   1. XOR-decode the obfuscated bytes sent by the ESP32 camera.
#   2. Run YOLO (best.pt) to find licence-plate bounding boxes.
#   3. For every detected plate: crop → grayscale → 2× upsample → PaddleOCR.
#   4. Push the annotated JPEG into latest_frame_plate so /stream_plate works.
#   5. Append each (text, confidence, bbox, timestamp) record to
#      sys_state["plates"]  (capped at PLATE_HISTORY_MAXLEN).
#   6. Return a JSON-serialisable dict to the route handler.
# ─────────────────────────────────────────────────────────────────────────────

import time
import threading
from typing import Any

import cv2
import numpy as np

try:
    from paddleocr import PaddleOCR
except ModuleNotFoundError:
    PaddleOCR = None

import smart_traffic.state as state

from ..config import PLATE_HISTORY_MAXLEN
from ..models import plate_model
from ..services.decode import decode_image
from ..state import infer_lock, sys_state


# ── PaddleOCR singleton (initialised once, reused across requests) ────────────
_ocr_lock = threading.Lock()
_ocr: Any | None = None


def _get_ocr():
    global _ocr
    if PaddleOCR is None:
        raise RuntimeError(
            "paddleocr is not installed. Install it with "
            "'pip install paddleocr' to enable /detect_plate OCR."
        )
    if _ocr is None:
        with _ocr_lock:
            if _ocr is None:          # double-checked locking
                print("Loading PaddleOCR (English, angle classifier)…")
                _ocr = PaddleOCR(use_angle_cls=True, lang="en")
    return _ocr


# ── helpers ───────────────────────────────────────────────────────────────────

def _preprocess_crop(bgr_crop: np.ndarray) -> np.ndarray:
    """Grayscale + 2× upscale (improves OCR on small plates)."""
    gray = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2GRAY)
    upscaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(upscaled, cv2.COLOR_GRAY2BGR)


def _read_text(ocr: PaddleOCR, crop_bgr: np.ndarray) -> tuple[str, float]:
    """Run OCR and return (text, confidence).  Returns ("N/A", 0.0) on failure."""
    result = ocr.ocr(crop_bgr)
    if not result:
        return "N/A", 0.0

    # PaddleOCR ≥ 2.7 returns dicts; older versions return nested lists.
    first = result[0]
    if isinstance(first, dict):
        texts = first.get("rec_texts", [])
        scores = first.get("rec_scores", [])
        if texts:
            return str(texts[0]), float(scores[0]) if scores else 0.0
    elif isinstance(first, list) and first:
        # Legacy format: [ [ [box], (text, score) ], … ]
        inner = first[0]
        if inner and len(inner) >= 2:
            text, score = inner[1]
            return str(text), float(score)

    return "N/A", 0.0


# ── public API ────────────────────────────────────────────────────────────────

def process_plate_data(obfuscated_bytes: bytes) -> dict:
    """
    Decode, detect, OCR, and return plate results.

    Returns a dict with keys:
        plates_this_frame  – list of {text, confidence, bbox} found in this image
        total_plates       – cumulative count stored in sys_state["plates"]
        command            – passthrough of current traffic command
    """
    if not sys_state["detection"]:
        return {
            "plates_this_frame": [],
            "total_plates": len(sys_state["plates"]),
            "command": sys_state["command"],
        }

    image = decode_image(obfuscated_bytes)           # PIL Image (RGB)
    # Convert to BGR numpy array for cv2 / YOLO
    frame_bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    # ── YOLO inference ────────────────────────────────────────────────────────
    with infer_lock:
        results = plate_model.predict(
            source=image,
            imgsz=640,
            conf=0.25,
            save=False,
        )

    annotated = results[0].plot()   # BGR numpy array with bboxes drawn

    # ── Push annotated frame for /stream_plate ─────────────────────────────────
    ret, buf = cv2.imencode(".jpg", annotated)
    if ret:
        with state.frame_condition_car:          # reuse existing condition or use dedicated one
            state.latest_frame_plate = buf.tobytes()
            state.latest_frame_ts_plate = time.time()

    # ── OCR each detected plate ───────────────────────────────────────────────
    ocr = _get_ocr()
    plates_this_frame: list[dict] = []
    timestamp_ms = int(time.time() * 1000)

    if results[0].boxes is not None:
        img_h, img_w = frame_bgr.shape[:2]
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
            # Clamp to image bounds
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(img_w, x2), min(img_h, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            crop = frame_bgr[y1:y2, x1:x2]
            processed_crop = _preprocess_crop(crop)
            text, conf = _read_text(ocr, processed_crop)

            record = {
                "text": text,
                "confidence": round(conf, 3),
                "bbox": [x1, y1, x2, y2],
                "timestamp_ms": timestamp_ms,
            }
            plates_this_frame.append(record)
            print(f"[PlateOCR] {text!r}  conf={conf:.2f}  bbox={record['bbox']}")

    # ── Append to rolling history in sys_state ────────────────────────────────
    for rec in plates_this_frame:
        sys_state["plates"].append(rec)
        # Trim to max length (simple pop from front; deque would also work)
        while len(sys_state["plates"]) > PLATE_HISTORY_MAXLEN:
            sys_state["plates"].pop(0)

    return {
        "plates_this_frame": plates_this_frame,
        "total_plates": len(sys_state["plates"]),
        "command": sys_state["command"],
    }
