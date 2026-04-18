import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC_PATH = os.path.join(BASE_DIR, 'logic.py')

CAR_MODEL_PATH = os.path.join(BASE_DIR, 'yolov8n.pt')
PERSON_MODEL_PATH = os.path.join(BASE_DIR, 'person_wheelchair_personWheelchairV2.pt')
PLATE_MODEL_PATH = os.path.join(BASE_DIR, 'license_plate.pt')   # ← NEW

XOR_KEY = b"MyIoTKey2026"
STREAM_ONLINE_TTL_SEC = 5.0
CAR_TARGET_CLASSES = [2, 3, 5, 7]
EDITOR_URL = (os.environ.get("STL_EDITOR_URL") or "https://stledit.gyke.net/").strip()

CAR_LANE_REGION_COUNT = 2
TIDAL_SAMPLE_WINDOW = 12
TIDAL_BIAS_MARGIN = 1.0

# Perspective-aware split boundary for 2-lane split.
# These defaults are the midpoint between the previous two-line boundaries.
LANE_SPLIT_TOP_RATIO = 0.50
LANE_SPLIT_BOTTOM_RATIO = 0.495

# Licence-plate OCR — max unique plates kept in sys_state["plates"]
PLATE_HISTORY_MAXLEN = 50
