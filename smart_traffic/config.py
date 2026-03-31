import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC_PATH = os.path.join(BASE_DIR, 'logic.py')

CAR_MODEL_PATH = os.path.join(BASE_DIR, 'yolov8n.pt')
PERSON_MODEL_PATH = os.path.join(BASE_DIR, 'person_wheelchair_personWheelchairV2.pt')
PLATE_MODEL_PATH = os.path.join(BASE_DIR, 'license_plate.pt')   # ← NEW

XOR_KEY = b"MyIoTKey2026"
STREAM_ONLINE_TTL_SEC = 5.0
CAR_TARGET_CLASSES = [2, 3, 5, 7]

CAR_LANE_REGION_COUNT = 3
TIDAL_SAMPLE_WINDOW = 12
TIDAL_BIAS_MARGIN = 1.0

# Perspective-aware lane boundaries for 3-lane split.
LANE_BOUNDARY1_TOP_RATIO = 0.43
LANE_BOUNDARY1_BOTTOM_RATIO = 0.33
LANE_BOUNDARY2_TOP_RATIO = 0.57
LANE_BOUNDARY2_BOTTOM_RATIO = 0.66

# Licence-plate OCR — max unique plates kept in sys_state["plates"]
PLATE_HISTORY_MAXLEN = 50
