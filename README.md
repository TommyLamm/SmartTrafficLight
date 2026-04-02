# Smart Traffic — AI-Powered Traffic Signal Control System

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00CFFF)](https://ultralytics.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

🌐 **Language / 語言：** English | [中文](README.zh-TW.md)

---

This project uses YOLOv8 to detect vehicles, pedestrians, and wheelchair users in real time, and dynamically determines traffic signal commands.  
The system provides a web dashboard, AUTO/MANUAL modes, and a hot-reloadable `logic.py` algorithm editor.

---

## Table of Contents

- [System Overview](#system-overview)
- [Hardware Roles (Mega & ESP32)](#hardware-roles-mega--esp32)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [API Endpoints](#api-endpoints)
- [Digital Twin MVP](#digital-twin-mvp)
- [Simulate Car Stream from a Real Road Video](#simulate-car-stream-from-a-real-road-video)
- [Basic Data Flow](#basic-data-flow)

---

## System Overview

- **Dual-Stream AI Detection**
  - Vehicle stream: `/detect_car`
  - Pedestrian/wheelchair stream: `/detect_person`
- **Signal Control Strategy**
  - Wheelchair priority (can trigger `PED_GREEN_30`)
  - Pedestrian volume triggers short/long crossing green lights
  - Switches to `CAR_GREEN` when vehicle traffic is dominant
- **Control Modes**
  - `AUTO`: Automatic decision-making via `logic.py`
  - `MANUAL`: Manual commands issued through the dashboard
- **Hot Reload**
  - Edits to `logic.py` can be applied instantly via `/save_code` without restarting the main service

---

## Hardware Roles (Mega & ESP32)

### 1) Arduino Mega (Signal Controller)

`ArduinoMega/ArduinoMega.ino` manages the physical signal light state machine and failsafe:

- Receives commands from the ESP32 via `Serial1` (e.g. `[CAR_GREEN]`, `[PED_GREEN_10]`)
- Controls state transitions for vehicle and pedestrian RGB lights
- Enters a failsafe loop (default safe timing sequence) if no valid heartbeat/command is received within the timeout period

### 2) ESP32S3-CAM_Person (Pedestrian/Wheelchair Node)

`ESP32S3-CAM_Person/ESP32S3-CAM_Person.ino`:

- Captures camera frames and obfuscates them via XOR (`MyIoTKey2026`)
- Uploads frames to `POST /detect_person`
- Parses the `command` field from the server's JSON response
- Wraps the command as `[COMMAND]` and sends it to the Arduino Mega over `Serial`

### 3) ESP32S3-CAM_Car (Vehicle Node)

`ESP32S3-CAM_Car/ESP32S3-CAM_Car.ino`:

- Captures camera frames and obfuscates them using the same XOR method
- Uploads frames to `POST /detect_car`
- Forwards emergency start/clear events from Mega to backend (`/trigger_emergency`, `/clear_emergency`) to keep web state in sync with hardware phases

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
├── ArduinoMega/
│   └── ArduinoMega.ino
├── ESP32S3-CAM_Car/
│   └── ESP32S3-CAM_Car.ino
├── ESP32S3-CAM_Person/
│   └── ESP32S3-CAM_Person.ino
└── smart_traffic/
    ├── config.py
    ├── models.py
    ├── state.py
    ├── services/
    └── web/
```

---

## Installation & Setup

### Requirements

- Python 3.10+
- CUDA recommended (optional, for accelerated inference)

### Install Dependencies

```bash
pip install flask waitress ultralytics opencv-python pillow numpy
```

### Model Files

Place the model files in the project root directory:

- `yolov8n.pt` (vehicle detection)
- `person_wheelchair_personWheelchairV2.pt` (pedestrian/wheelchair detection)

### Start the Server

```bash
python app.py
```

Once running:

- Main dashboard: `http://127.0.0.1:5000`
- Algorithm editor: `http://127.0.0.1:5001`

---

## API Endpoints

### Detection

- `POST /detect_person` — Upload pedestrian/wheelchair frames (`application/octet-stream`)
- `POST /detect_car` — Upload vehicle frames
- `POST /detect_all` — Legacy compatibility (currently redirects to the pedestrian pipeline)

### Streams & Status

- `GET /video_feed_person` — Pedestrian video stream
- `GET /video_feed_car` — Vehicle video stream
- `GET /video_feed` — Legacy compatibility (pedestrian stream)
- `GET /stats` — Returns system status (includes `mode`, `command`, `stream_*_online`)

### Control

- `POST /set_mode` — Switch between `AUTO` and `MANUAL` modes
- `POST /manual_override` — Send a manual signal command
- `POST /toggle_detection` — Toggle AI detection on/off
- `POST /toggle_emergency` — Enable/disable emergency-priority feature
- `POST /toggle_wheelchair_priority` — Enable/disable adaptive wheelchair timing
- `POST /trigger_emergency` — Start emergency 3-phase state (`YELLOW -> ALL_RED -> HOLD`)
- `POST /clear_emergency` — Clear emergency state and resume normal logic
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

---

## Basic Data Flow

1. The ESP32-CAM captures frames, obfuscates them via XOR, and uploads them to the Flask API.
2. The server decodes the frames, runs YOLO inference, and updates the system state.
3. The pedestrian pipeline computes a `command` according to `logic.py`.
4. The Car node forwards the current `command` in serial format to the Arduino Mega.
5. The Arduino Mega switches the physical signal lights according to the command.

---

## License

MIT License © 2026
