import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIC_PATH = os.path.join(BASE_DIR, 'logic.py')

CAR_MODEL_PATH = os.path.join(BASE_DIR, 'yolov8n.pt')
PERSON_MODEL_PATH = os.path.join(BASE_DIR, 'person_wheelchair_personWheelchair.pt')

XOR_KEY = b"MyIoTKey2026"
STREAM_ONLINE_TTL_SEC = 5.0
CAR_TARGET_CLASSES = [2, 3, 5, 7]
