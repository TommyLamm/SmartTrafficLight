import numpy as np
import requests
from PIL import Image
import io

XOR_KEY = b"MyIoTKey2026"

def encode_image(image_path: str) -> bytes:
    """XOR-encode a local image file the same way the ESP32 would."""
    with open(image_path, "rb") as f:
        raw = f.read()
    input_arr = np.frombuffer(raw, dtype=np.uint8)
    key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
    return np.bitwise_xor(input_arr, key_arr).tobytes()

# ← Point this to your test photo
IMAGE_PATH = "/root/andy_branch/SmartTrafficLight/test_material/images.jpg"

encoded = encode_image(IMAGE_PATH)

response = requests.post(
    "http://127.0.0.1:5000/detect_plate",
    data=encoded,
    headers={"Content-Type": "application/octet-stream"},
)

print("Status:", response.status_code)
print("Result:", response.json())
