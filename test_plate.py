import requests
import numpy as np

XOR_KEY = b"MyIoTKey2026"

# Load any JPEG image and XOR-obfuscate it
with open("/root/beta_branch/SmartTrafficLight/test_material/下載.jpg", "rb") as f:
    raw = f.read()

input_arr = np.frombuffer(raw, dtype=np.uint8)
key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
obfuscated = np.bitwise_xor(input_arr, key_arr).tobytes()

response = requests.post(
    "http://127.0.0.1:5000/capture_violation",
    data=obfuscated,
    headers={"Content-Type": "application/octet-stream"}
)
print(response.json())
