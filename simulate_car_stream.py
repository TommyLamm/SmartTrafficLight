#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

XOR_KEY = b"MyIoTKey2026"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Replay a recorded road video as the Car Detection stream "
            "by posting XOR-obfuscated JPEG frames to /detect_car."
        )
    )
    parser.add_argument("--video-path", required=True, help="Path to a local video file (mp4/mov/avi/...).")
    parser.add_argument("--server-url", default="http://127.0.0.1:5000", help="Base URL of SmartTraffic server.")
    parser.add_argument("--fps", type=float, default=8.0, help="Max frame upload FPS. Use <=0 to disable cap.")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier (e.g. 2.0 = 2x).")
    parser.add_argument("--loop", action="store_true", help="Loop the video after it reaches EOF.")
    parser.add_argument("--duration-sec", type=float, default=0.0, help="Stop after N seconds (0 = no limit).")
    parser.add_argument("--resize-width", type=int, default=960, help="Resize frame width before upload (0 = keep source size).")
    parser.add_argument("--jpeg-quality", type=int, default=85, help="JPEG quality [1..100].")
    parser.add_argument("--request-timeout", type=float, default=8.0, help="HTTP timeout per request in seconds.")
    parser.add_argument("--log-interval-sec", type=float, default=2.0, help="Print progress every N seconds.")
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=15,
        help="Abort if this many frame uploads fail in a row.",
    )
    parser.add_argument(
        "--mirror-to-person",
        action="store_true",
        help=(
            "Also post each frame to /detect_person. Useful for demo environments "
            "without an actual person camera so command/light_state still updates."
        ),
    )
    parser.add_argument(
        "--keep-mode",
        action="store_true",
        help="Do not force /set_mode to AUTO at startup.",
    )
    parser.add_argument(
        "--no-ensure-detection",
        action="store_true",
        help="Skip auto-checking /stats and toggling detection ON when needed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pacing/encoding pipeline without HTTP uploads.",
    )
    return parser.parse_args()


def build_url(server_url, endpoint):
    base = server_url.rstrip("/")
    path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    return f"{base}{path}"


def xor_obfuscate(raw_bytes):
    key_len = len(XOR_KEY)
    output = bytearray(len(raw_bytes))
    for idx, value in enumerate(raw_bytes):
        output[idx] = value ^ XOR_KEY[idx % key_len]
    return bytes(output)


def _decode_json_bytes(body):
    if not body:
        return {}
    text = body.decode("utf-8", errors="replace")
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}
    if isinstance(decoded, dict):
        return decoded
    return {"value": decoded}


def request_json(server_url, endpoint, method="GET", payload=None, timeout_sec=8.0):
    url = build_url(server_url, endpoint)
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request_obj = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout_sec) as resp:
            status = int(resp.getcode())
            body = resp.read()
        return True, status, _decode_json_bytes(body), ""
    except urllib.error.HTTPError as exc:
        body = exc.read()
        parsed = _decode_json_bytes(body)
        return False, int(exc.code), parsed, f"HTTP {exc.code} on {endpoint}"
    except urllib.error.URLError as exc:
        return False, 0, {}, f"Connection error on {endpoint}: {exc.reason}"
    except socket.timeout:
        return False, 0, {}, f"Timeout on {endpoint}"


def post_frame(server_url, endpoint, payload, timeout_sec=8.0):
    url = build_url(server_url, endpoint)
    request_obj = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout_sec) as resp:
            status = int(resp.getcode())
            body = resp.read()
        return True, status, _decode_json_bytes(body), ""
    except urllib.error.HTTPError as exc:
        body = exc.read()
        parsed = _decode_json_bytes(body)
        return False, int(exc.code), parsed, f"HTTP {exc.code} on {endpoint}"
    except urllib.error.URLError as exc:
        return False, 0, {}, f"Connection error on {endpoint}: {exc.reason}"
    except socket.timeout:
        return False, 0, {}, f"Timeout on {endpoint}"


def ensure_runtime_state(server_url, timeout_sec=8.0, keep_mode=False, ensure_detection=True):
    ok, status, stats, err = request_json(server_url, "/stats", method="GET", timeout_sec=timeout_sec)
    if not ok:
        raise RuntimeError(f"Cannot read /stats (status={status}): {err}")
    if "detection" not in stats:
        raise RuntimeError("/stats response missing 'detection'.")
    if "mode" not in stats:
        raise RuntimeError("/stats response missing 'mode'.")

    if ensure_detection and not bool(stats["detection"]):
        ok, status, payload, err = request_json(
            server_url,
            "/toggle_detection",
            method="POST",
            timeout_sec=timeout_sec,
        )
        if not ok:
            raise RuntimeError(f"Failed to enable detection (status={status}): {err} {payload}")
        if not bool(payload.get("detection", False)):
            raise RuntimeError("Detection toggle request succeeded but detection is still OFF.")
        print("[sim] detection was OFF, toggled to ON.", flush=True)

    if not keep_mode and str(stats["mode"]) != "AUTO":
        ok, status, payload, err = request_json(
            server_url,
            "/set_mode",
            method="POST",
            payload={"mode": "AUTO"},
            timeout_sec=timeout_sec,
        )
        if not ok:
            raise RuntimeError(f"Failed to set AUTO mode (status={status}): {err} {payload}")
        if str(payload.get("mode")) != "AUTO":
            raise RuntimeError("set_mode returned success but mode is not AUTO.")
        print("[sim] mode was not AUTO, switched to AUTO.", flush=True)


def encode_frame(frame, resize_width, jpeg_quality, cv2_mod):
    output_frame = frame
    if resize_width > 0 and frame.shape[1] != resize_width:
        scale = float(resize_width) / float(frame.shape[1])
        new_height = max(1, int(round(frame.shape[0] * scale)))
        output_frame = cv2_mod.resize(frame, (resize_width, new_height), interpolation=cv2_mod.INTER_AREA)

    ok, encoded = cv2_mod.imencode(
        ".jpg",
        output_frame,
        [int(cv2_mod.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
    )
    if not ok:
        raise RuntimeError("OpenCV failed to JPEG-encode a video frame.")
    return encoded.tobytes()


def main():
    args = parse_args()
    try:
        import cv2 as cv2_mod
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "OpenCV (cv2) is not installed. Install dependencies first, e.g. "
            "'pip install opencv-python'."
        ) from exc

    if not os.path.isfile(args.video_path):
        raise FileNotFoundError(f"Video file not found: {args.video_path}")
    if args.speed <= 0:
        raise ValueError("--speed must be > 0")
    if args.jpeg_quality < 1 or args.jpeg_quality > 100:
        raise ValueError("--jpeg-quality must be in [1, 100]")
    if args.max_consecutive_errors < 1:
        raise ValueError("--max-consecutive-errors must be >= 1")

    cap = cv2_mod.VideoCapture(args.video_path)
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV cannot open video: {args.video_path}")

    try:
        source_fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
        if source_fps <= 0.0:
            source_fps = 30.0
        source_frame_count = int(cap.get(cv2_mod.CAP_PROP_FRAME_COUNT) or 0)
        source_duration_sec = (
            float(source_frame_count) / source_fps
            if source_frame_count > 0
            else (1.0 / source_fps)
        )

        if not args.dry_run:
            ensure_runtime_state(
                server_url=args.server_url,
                timeout_sec=args.request_timeout,
                keep_mode=args.keep_mode,
                ensure_detection=not args.no_ensure_detection,
            )

        print(
            (
                "[sim] starting stream: video=%s source_fps=%.2f upload_fps=%s speed=%.2fx "
                "mirror_to_person=%s dry_run=%s"
            )
            % (
                args.video_path,
                source_fps,
                ("unlimited" if args.fps <= 0 else f"{args.fps:.2f}"),
                args.speed,
                args.mirror_to_person,
                args.dry_run,
            ),
            flush=True,
        )

        stream_start_wall = time.monotonic()
        stop_at_wall = (
            stream_start_wall + args.duration_sec
            if args.duration_sec and args.duration_sec > 0
            else None
        )

        frame_index = 0
        frame_index_loop = 0
        sent_frames = 0
        loop_count = 0
        consecutive_errors = 0
        last_send_wall = 0.0
        last_state = {}
        next_log_wall = stream_start_wall + max(0.5, args.log_interval_sec)

        while True:
            if stop_at_wall is not None and time.monotonic() >= stop_at_wall:
                print("[sim] duration reached, stopping.", flush=True)
                break

            ok_read, frame = cap.read()
            if not ok_read:
                if args.loop:
                    loop_count += 1
                    cap.release()
                    cap = cv2_mod.VideoCapture(args.video_path)
                    if not cap.isOpened():
                        raise RuntimeError(
                            f"OpenCV failed to reopen video during loop: {args.video_path}"
                        )
                    frame_index_loop = 0
                    continue
                print("[sim] reached end of video.", flush=True)
                break

            frame_index += 1
            frame_index_loop += 1

            timeline_elapsed_sec = (
                (loop_count * source_duration_sec) + (frame_index_loop / source_fps)
            ) / args.speed
            due_wall = stream_start_wall + timeline_elapsed_sec
            now_wall = time.monotonic()
            if due_wall > now_wall:
                time.sleep(due_wall - now_wall)

            if args.fps > 0 and last_send_wall > 0:
                min_interval = 1.0 / args.fps
                now_wall = time.monotonic()
                gap = now_wall - last_send_wall
                if gap < min_interval:
                    time.sleep(min_interval - gap)

            jpeg = encode_frame(frame, args.resize_width, args.jpeg_quality, cv2_mod)
            payload = xor_obfuscate(jpeg)

            if args.dry_run:
                sent_frames += 1
                last_send_wall = time.monotonic()
            else:
                ok_car, status_car, data_car, err_car = post_frame(
                    args.server_url,
                    "/detect_car",
                    payload,
                    timeout_sec=args.request_timeout,
                )
                if not ok_car:
                    consecutive_errors += 1
                    print(
                        f"[sim] /detect_car failed ({consecutive_errors}/{args.max_consecutive_errors}): "
                        f"status={status_car} err={err_car} payload={data_car}",
                        flush=True,
                    )
                    if consecutive_errors >= args.max_consecutive_errors:
                        raise RuntimeError("Too many consecutive upload failures.")
                    continue

                last_state = dict(data_car)
                if args.mirror_to_person:
                    ok_person, status_person, data_person, err_person = post_frame(
                        args.server_url,
                        "/detect_person",
                        payload,
                        timeout_sec=args.request_timeout,
                    )
                    if not ok_person:
                        consecutive_errors += 1
                        print(
                            f"[sim] /detect_person failed ({consecutive_errors}/{args.max_consecutive_errors}): "
                            f"status={status_person} err={err_person} payload={data_person}",
                            flush=True,
                        )
                        if consecutive_errors >= args.max_consecutive_errors:
                            raise RuntimeError("Too many consecutive upload failures.")
                        continue
                    last_state.update(data_person)

                consecutive_errors = 0
                sent_frames += 1
                last_send_wall = time.monotonic()

            now_wall = time.monotonic()
            if now_wall >= next_log_wall:
                if args.dry_run:
                    print(
                        f"[sim] sent={sent_frames} read={frame_index} loops={loop_count}",
                        flush=True,
                    )
                else:
                    print(
                        "[sim] sent=%d read=%d loops=%d cars=%s persons=%s wheelchairs=%s command=%s"
                        % (
                            sent_frames,
                            frame_index,
                            loop_count,
                            last_state.get("cars", "?"),
                            last_state.get("persons", "?"),
                            last_state.get("wheelchairs", "?"),
                            last_state.get("command", "?"),
                        ),
                        flush=True,
                    )
                next_log_wall = now_wall + max(0.5, args.log_interval_sec)

        elapsed = time.monotonic() - stream_start_wall
        print(
            "[sim] finished: sent=%d read=%d loops=%d elapsed=%.1fs"
            % (sent_frames, frame_index, loop_count, elapsed),
            flush=True,
        )
        return 0
    finally:
        cap.release()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"[sim] fatal: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
