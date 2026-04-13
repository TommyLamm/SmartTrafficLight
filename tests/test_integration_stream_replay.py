import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2
import numpy as np

import simulate_car_stream


class _ReplayStubHandler(BaseHTTPRequestHandler):
    detect_car_hits = 0
    detect_person_hits = 0

    def _write_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/stats"):
            self._write_json(200, {"detection": True, "mode": "AUTO"})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", "0") or "0")
        if content_len > 0:
            _ = self.rfile.read(content_len)

        if self.path == "/detect_car":
            _ReplayStubHandler.detect_car_hits += 1
            self._write_json(
                200,
                {"cars": 1, "persons": 0, "wheelchairs": 0, "command": "KEEP"},
            )
            return

        if self.path == "/detect_person":
            _ReplayStubHandler.detect_person_hits += 1
            self._write_json(
                200,
                {"cars": 1, "persons": 0, "wheelchairs": 0, "command": "KEEP"},
            )
            return

        if self.path == "/toggle_detection":
            self._write_json(200, {"success": True, "detection": True})
            return

        if self.path == "/set_mode":
            self._write_json(200, {"success": True, "mode": "AUTO"})
            return

        self._write_json(404, {"error": "not found"})

    def log_message(self, format, *args):
        return


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _create_tiny_video(video_path: Path):
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(video_path), fourcc, 10.0, (64, 48))
    if not writer.isOpened():
        raise RuntimeError("Cannot create test video writer")
    try:
        for idx in range(12):
            frame = np.full((48, 64, 3), idx * 10, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


def test_simulate_car_stream_replays_to_http_stub(monkeypatch, tmp_path):
    _ReplayStubHandler.detect_car_hits = 0
    _ReplayStubHandler.detect_person_hits = 0

    video_path = tmp_path / "tiny_replay.avi"
    _create_tiny_video(video_path)
    assert video_path.exists()

    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), _ReplayStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    args = [
        "simulate_car_stream.py",
        "--video-path",
        str(video_path),
        "--server-url",
        f"http://127.0.0.1:{port}",
        "--fps",
        "6",
        "--duration-sec",
        "1.2",
        "--resize-width",
        "64",
        "--jpeg-quality",
        "80",
        "--log-interval-sec",
        "0.5",
        "--mirror-to-person",
    ]
    monkeypatch.setattr("sys.argv", args)

    try:
        exit_code = simulate_car_stream.main()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

    assert exit_code == 0
    assert _ReplayStubHandler.detect_car_hits > 0
    assert _ReplayStubHandler.detect_person_hits > 0

