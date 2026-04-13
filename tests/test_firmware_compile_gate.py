import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _compile_sketch(root: Path, fqbn: str, sketch_dir: str):
    sketch_path = root / sketch_dir
    proc = subprocess.run(
        ["arduino-cli", "compile", "--fqbn", fqbn, str(sketch_path)],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Compile failed for {sketch_dir} ({fqbn})\n"
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )


@pytest.mark.skipif(shutil.which("arduino-cli") is None, reason="arduino-cli not installed")
def test_optional_firmware_compile_gate():
    if os.environ.get("RUN_ARDUINO_COMPILE") != "1":
        pytest.skip("Set RUN_ARDUINO_COMPILE=1 to enable firmware compile gate.")

    root = Path(__file__).resolve().parents[1]
    mega_fqbn = os.environ.get("MEGA_FQBN", "arduino:avr:mega")
    esp32cam_fqbn = os.environ.get("ESP32CAM_FQBN", "esp32:esp32:esp32cam")

    _compile_sketch(root, mega_fqbn, "ArduinoMega")
    _compile_sketch(root, esp32cam_fqbn, "ESP32S3-CAM_Person")
    _compile_sketch(root, esp32cam_fqbn, "ESP32S3-CAM_Car")

