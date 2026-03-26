import io

import numpy as np
from PIL import Image

from ..config import XOR_KEY


def decode_image(obfuscated_bytes):
    input_arr = np.frombuffer(obfuscated_bytes, dtype=np.uint8)
    key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
    decrypted_bytes = np.bitwise_xor(input_arr, key_arr).tobytes()
    return Image.open(io.BytesIO(decrypted_bytes))
