"""Tests for smart_traffic.services.decode — XOR obfuscation/deobfuscation."""

import io

import numpy as np
import pytest
from PIL import Image

from smart_traffic.config import XOR_KEY
from smart_traffic.services.decode import decode_image


def _obfuscate(raw_bytes: bytes) -> bytes:
    """Apply the same XOR obfuscation the ESP32 cameras use."""
    key = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(raw_bytes))
    src = np.frombuffer(raw_bytes, dtype=np.uint8)
    return np.bitwise_xor(src, key).tobytes()


def _make_jpeg(width=32, height=24, color=(100, 150, 200)) -> bytes:
    """Create a minimal valid JPEG in memory."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── Roundtrip: encode → decode → verify ──────────────────────────────────────

def test_decode_image_roundtrip_produces_correct_dimensions():
    """XOR-encode a 32×24 JPEG, decode it back, verify size matches."""
    raw = _make_jpeg(32, 24)
    obfuscated = _obfuscate(raw)
    result = decode_image(obfuscated)

    assert isinstance(result, Image.Image)
    assert result.size == (32, 24)
    assert result.mode == "RGB"


def test_decode_image_roundtrip_preserves_pixel_data():
    """Pixel values should survive the XOR roundtrip (within JPEG tolerance)."""
    raw = _make_jpeg(8, 8, color=(255, 0, 0))
    obfuscated = _obfuscate(raw)
    result = decode_image(obfuscated)

    # Center pixel of an 8×8 solid-red image should still be roughly red
    r, g, b = result.getpixel((4, 4))
    assert r > 200, f"Red channel too low: {r}"
    assert g < 50, f"Green channel too high: {g}"
    assert b < 50, f"Blue channel too high: {b}"


def test_decode_image_double_xor_returns_original():
    """XOR is its own inverse: encode(encode(x)) == x."""
    raw = _make_jpeg(16, 16)
    double_encoded = _obfuscate(_obfuscate(raw))
    # Double XOR should return the original bytes exactly
    assert double_encoded == raw


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_decode_image_rejects_empty_payload():
    """Empty obfuscated bytes should raise an error (not a valid JPEG)."""
    with pytest.raises(Exception):
        decode_image(b"")


def test_decode_image_rejects_corrupted_payload():
    """Random non-JPEG bytes should fail to decode."""
    garbage = _obfuscate(b"this is not a jpeg at all!!")
    with pytest.raises(Exception):
        decode_image(garbage)


def test_decode_image_handles_large_image():
    """Verify decode works with a larger image (640×480)."""
    raw = _make_jpeg(640, 480)
    obfuscated = _obfuscate(raw)
    result = decode_image(obfuscated)
    assert result.size == (640, 480)
