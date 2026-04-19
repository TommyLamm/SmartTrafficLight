# Smart Traffic — AI-Powered Traffic Signal Control System

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00CFFF)](https://ultralytics.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

🌐 **Language / 語言：** English | [中文](README.zh-TW.md)

---

This project uses YOLOv8 to detect vehicles, pedestrians, and wheelchair users in real time, and dynamically determines traffic signal commands.  
The system also includes license-plate OCR, violation capture, lane-boundary tuning, a Digital Twin sandbox, and a hot-reloadable `logic.py` algorithm editor.

---

## Table of Contents

- [System Overview](#system-overview)
- [Hardware Roles (Mega, ESP32-CAM, ESP8266)](#hardware-roles-mega-esp32-cam-esp8266)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [API Endpoints](#api-endpoints)
- [Digital Twin MVP](#digital-twin-mvp)
- [Simulate Car Stream from a Real Road Video](#simulate-car-stream-from-a-real-road-video)
- [Basic Data Flow](#basic-data-flow)

---

## System Overview

- **Multi-Stream AI Detection**
  - Vehicle stream: `/detect_car`
  - Pedestrian/wheelchair stream: `/detect_person`
  - Plate OCR stream: `/detect_plate`
- **Signal Control Strategy**
  - Wheelchair priority (can trigger `PED_GREEN_30`)
  - Pedestrian volume triggers short/long crossing green lights
  - Switches to `CAR_GREEN` when vehicle traffic is dominant
  - Supports emergency 3-phase sequence (`EMERGENCY_YELLOW -> EMERGENCY_ALL_RED -> EMERGENCY_RED`)
- **Traffic Analytics & Operations**
  - Two-lane directional analytics (`lane_counts`, `tidal_direction`)
  - Adjustable lane split boundary via `/lane_boundaries`
  - Violation capture records with image browsing (`/capture_violation`, `/violations`)
  - Rolling license-plate history (`/plates`)
- **Control Modes**
  - `AUTO`: Automatic decision-making via `logic.py`
  - `MANUAL`: Dashboard commands are latched and kept in `/stats` until changed or mode switches
- **Hot Reload**
  - Edits to `logic.py` can be applied instantly via `/save_code` without restarting the main service

---

## Hardware Roles (Mega, ESP32-CAM, ESP8266)

### 1) Arduino Mega (Signal Controller)

`ArduinoMega/ArduinoMega.ino` manages the physical signal light state machine and failsafe:

- Polls `GET /stats?client=mega` through an ESP8266 AT module (`Serial2`, pins 16/17) and consumes compact control payloads
- Mirrors backend control mode in serial status (`[AI-Smart]` / `[MANUAL]`), with `[Failsafe]` taking priority
- Controls state transitions for vehicle and pedestrian RGB lights
- Reads local sensors on Mega: pressure (`A0`), RFID (SPI, `SS=53`, `RST=49`), illuminance (`A1`)
- Runs emergency/failsafe logic locally (including emergency-clear translation when server command returns to non-emergency)
- Enters a failsafe loop if no valid server heartbeat/command is received within timeout

### 2) ESP32S3-CAM_Person (Pedestrian/Wheelchair Node)

`ESP32S3-CAM_Person/ESP32S3-CAM_Person.ino`:

- Captures camera frames and obfuscates them via XOR (`MyIoTKey2026`)
- Uploads frames to `POST /detect_person`
- Does not control Mega directly over UART in the current architecture

### 3) ESP32S3-CAM_Car (Vehicle Node)

`ESP32S3-CAM_Car/ESP32S3-CAM_Car.ino`:

- Captures camera frames and obfuscates them using the same XOR method
- Uploads frames to `POST /detect_car`
- Triggers violation capture uploads (`/capture_violation`)
- In current firmware, pressure/RFID local paths are disabled on this node (moved back to Mega)
- Does not forward control commands to Mega over UART

### 4) ESP8266 (AT WiFi Bridge for Mega)

- Runs stock AT firmware (no project-specific firmware flashing required)
- Connected to Mega `Serial2` and used via `WiFiEsp`
- Provides Mega's network path to poll backend `/stats?client=mega` and keep command heartbeat alive

**Mega `/stats` polling troubleshooting**
- In `ArduinoMega/ArduinoMega.ino`, set `WIFI_SSID` / `WIFI_PASS` correctly before flashing.
- Keep `SERVER_HOST="stl.gyke.net"` for normal operation; set `SERVER_FALLBACK_HOST` only when you need a fixed-IP fallback route.
- If serial logs show repeated `Not connected` or `Connect failed`, verify ESP8266 AT firmware, 3.3V power stability, and that TCP `:80` to backend is reachable from the same WiFi.
- New firmware diagnostics separate link state, TCP connect failure, HTTP timeout, and JSON parse failure to make root-cause isolation faster.

---

## Project Structure

```text
SmartTrafficLight/
├── app.py
├── logic.py
├── logic_editor.py
├── core.py
├── yolov8n.pt
├── person_wheelchair_personWheelchairV2.pt
├── license_plate.pt
├── ArduinoMega/
│   └── ArduinoMega.ino
├── ESP32S3-CAM_Car/
│   └── ESP32S3-CAM_Car.ino
├── ESP32S3-CAM_Person/
│   └── ESP32S3-CAM_Person.ino
├── simulate_car_stream.py
├── test_plate.py
└── smart_traffic/
    ├── __init__.py
    ├── config.py
    ├── models.py
    ├── state.py
    ├── services/
    ├── violations/
    └── web/
```

---

## Installation & Setup

### Requirements

- Python 3.10+
- CUDA recommended (optional, for accelerated inference)

### Install Dependencies

```bash
pip install flask waitress ultralytics opencv-python pillow numpy requests
```

Optional (required for plate OCR / violation OCR features):

```bash
pip install paddleocr paddlepaddle
```

### Model Files

Place the model files in the project root directory:

- `yolov8n.pt` (vehicle detection)
- `person_wheelchair_personWheelchairV2.pt` (pedestrian/wheelchair detection)
- `license_plate.pt` (license-plate detection)

### Start the Server

```bash
python app.py
```

Once running:

- Main dashboard: `http://127.0.0.1:5000`
- Algorithm editor: `http://127.0.0.1:5001`
- Optional (dashboard Edit button target): set env `STL_EDITOR_URL` (default: `https://stledit.gyke.net/`)

Notes:

- `app.py` starts `logic_editor.py` automatically if present.
- If PaddleOCR is not installed, `/detect_plate` and `/capture_violation` plate OCR paths will return runtime errors.

---

## API Endpoints

### Detection

- `POST /detect_person` — Upload pedestrian/wheelchair frames (`application/octet-stream`)
- `POST /detect_car` — Upload vehicle frames
- `POST /detect_plate` — Upload frames for plate detection + OCR
- `POST /capture_violation` — Upload HD violation snapshots (stores image + metadata)
- `POST /detect_all` — Legacy compatibility (currently redirects to the pedestrian pipeline)
- `GET /plates` — Rolling history of plate OCR results

### Streams & Status

- `GET /video_feed_person` — Pedestrian video stream
- `GET /video_feed_car` — Vehicle video stream
- `GET /stream_plate` — Plate-annotated MJPEG stream
- `GET /video_feed` — Legacy compatibility (pedestrian stream)
- `GET /stats` — Returns full system status (includes `mode`, `command`, `cars_total`, `lane_counts`, `tidal_direction`, `sample_window`, `stream_*_online`, `lane_boundaries`, `plates_count`, Digital Twin flags)
- `GET /stats?client=mega` — Compact payload for Arduino Mega polling

### Control

- `POST /set_mode` — Switch between `AUTO` and `MANUAL` modes
- `POST /manual_override` — Send a manual signal command
- `POST /toggle_detection` — Toggle AI detection on/off
- `POST /toggle_emergency` — Enable/disable emergency-priority feature (when off, Mega ignores RFID/server emergency triggers)
- `POST /toggle_wheelchair_priority` — Enable/disable adaptive wheelchair timing
- `POST /trigger_emergency` — Start emergency 3-phase state (`YELLOW -> ALL_RED -> HOLD`)
- `POST /clear_emergency` — Clear emergency state and resume normal logic
- `GET /lane_boundaries` — Get current two-lane split boundary (`boundary_top`, `boundary_bottom`, revision metadata)
- `POST /lane_boundaries` — Update lane split boundary ratios
- `GET /violations` — List captured violation records
- `GET /violation_image/<filename>` — Fetch a stored violation image

### Editor

- `GET /get_code` — Read current `logic.py`
- `POST /save_code` — Save and hot-reload `logic.py`

---

### Digital Twin MVP

- `POST /digital_twin/start` — Start recording live traffic snapshots (JSON accepts `max_frames`)
- `POST /digital_twin/stop` — Stop recording
- `POST /digital_twin/clear` — Clear recorded snapshots
- `GET /digital_twin/session` — Current recording session status
- `GET /digital_twin/frames` — Raw recorded snapshots (supports `?limit=200`)
- `GET /digital_twin/playback` — Timeline-oriented playback payload (supports `?limit=600`)
- `POST /digital_twin/compare` — What-if strategy comparison (`baseline`, `pedestrian_first`, `vehicle_first`, `balanced_flow`)

---

## Simulate Car Stream from a Real Road Video

You can run the whole system without ESP32 hardware by replaying a prerecorded road video into the same API protocol used by the camera node.

### 1) Start server

```bash
python app.py
```

### 2) Replay a video as `/detect_car`

```bash
python simulate_car_stream.py \
  --video-path ./path/to/road_video.mp4 \
  --server-url http://127.0.0.1:5000 \
  --fps 8 \
  --speed 1.0 \
  --loop
```

### 3) (Recommended for full demo) Mirror frames to `/detect_person`

`command/light_state` updates are triggered by the person pipeline in this architecture.  
If you only send `/detect_car`, lane statistics update but signal commands may not change as often.

```bash
python simulate_car_stream.py \
  --video-path ./path/to/road_video.mp4 \
  --fps 8 \
  --loop \
  --mirror-to-person
```

### 4) Verify system is running

- Dashboard (`http://127.0.0.1:5000`) updates in real time
- `/stats` shows changing `cars`, `lane_counts`, `tidal_direction`
- With `--mirror-to-person`, `command` and `light_state` should also evolve

### 5) Run Digital Twin on simulated traffic

```bash
curl -X POST http://127.0.0.1:5000/digital_twin/start -H 'Content-Type: application/json' -d '{"max_frames":1200}'
# wait a few seconds while simulator is streaming
curl -X POST http://127.0.0.1:5000/digital_twin/stop
curl -X POST http://127.0.0.1:5000/digital_twin/compare -H 'Content-Type: application/json' \
  -d '{"strategies":["baseline","pedestrian_first","vehicle_first","balanced_flow"]}'
```

Notes:
- `simulate_car_stream.py` uses the same XOR key (`MyIoTKey2026`) and `application/octet-stream` transport as ESP32.
- Use `--resize-width` and lower `--fps` if your machine is overloaded.
- Use `--keep-mode` if you do not want the simulator to force `AUTO` mode at startup.
- Use `--no-ensure-detection` if you do not want the simulator to auto-enable detection.

---

## Basic Data Flow

1. ESP32-CAM nodes (car/person) capture frames, obfuscate them via XOR, and upload to Flask APIs.
2. The server decodes frames, runs inference, and updates global traffic state (`command`, counts, lane data, stream online flags).
3. Plate and violation pipelines run YOLO + OCR and persist rolling metadata/images (`/plates`, `/violations`).
4. Dashboard users can tune lane boundaries (`boundary_top`, `boundary_bottom`) for 2-lane split analytics.
5. Arduino Mega polls backend `/stats?client=mega` through ESP8266 (AT + `WiFiEsp`) to fetch compact control payloads.
6. Mega parses `command`, `cars_total`, lane metrics, and mode/emergency flags, then updates local FSM context.
7. Mega executes physical signal switching and local sensor logic (RFID/pressure/illuminance/OLED).
8. If backend command flow is lost, Mega enters failsafe timing sequence.

---

## License

MIT License © 2026
