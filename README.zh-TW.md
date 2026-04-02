# Smart Traffic — AI 智慧交通號誌控制系統

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00CFFF)](https://ultralytics.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

🌐 **Language / 語言：** [English](README.md) | 繁體中文

---

本專案使用 YOLOv8 即時偵測車輛、行人與輪椅使用者，並動態決策交通號誌指令。  
系統提供 Web 儀表板、AUTO/MANUAL 模式，以及可熱重載的 `logic.py` 演算法編輯功能。

---

## 目錄

- [系統概述](#系統概述)
- [硬體角色說明（Mega 與 ESP32）](#硬體角色說明mega-與-esp32)
- [專案結構](#專案結構)
- [安裝與啟動](#安裝與啟動)
- [API 端點](#api-端點)
- [Digital Twin MVP](#digital-twin-mvp)
- [用真實道路影片模擬 Car Stream](#用真實道路影片模擬-car-stream)
- [基本資料流](#基本資料流)

---

## 系統概述

- **雙串流 AI 偵測**
  - 車流端：`/detect_car`
  - 行人/輪椅端：`/detect_person`
- **號誌控制策略**
  - 輪椅優先（可觸發 `PED_GREEN_30`）
  - 行人流量觸發短/長過街綠燈
  - 車流為主時切換 `CAR_GREEN`
- **控制模式**
  - `AUTO`：依 `logic.py` 自動決策
  - `MANUAL`：由介面送出手動指令
- **熱重載**
  - 編輯 `logic.py` 後可透過 `/save_code` 即時套用，不需重啟主服務

---

## 硬體角色說明（Mega 與 ESP32）

### 1) Arduino Mega（號誌控制器）

`ArduinoMega/ArduinoMega.ino` 負責實體號誌燈狀態機與 failsafe：

- 從 `Serial1` 接收來自 ESP32 的指令（格式如 `[CAR_GREEN]`、`[PED_GREEN_10]`）
- 控制車道與行人 RGB 燈的狀態切換
- 若超過逾時未收到有效心跳/指令，進入 failsafe 循環（預設安全時序）

### 2) ESP32S3-CAM_Person（行人/輪椅節點）

`ESP32S3-CAM_Person/ESP32S3-CAM_Person.ino`：

- 擷取相機影像並以 XOR（`MyIoTKey2026`）混淆
- 上傳到 `POST /detect_person`
- 解析伺服器回應 JSON 的 `command`
- 透過 `Serial` 將指令包成 `[COMMAND]` 發送給 Arduino Mega

### 3) ESP32S3-CAM_Car（車流節點）

`ESP32S3-CAM_Car/ESP32S3-CAM_Car.ino`：

- 擷取相機影像並以同樣 XOR 方式混淆
- 上傳到 `POST /detect_car`
- 會把 Mega 的 emergency 開始/結束事件轉發到後端（`/trigger_emergency`、`/clear_emergency`），讓 Web 狀態與實體燈同步

---

## 專案結構

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

## 安裝與啟動

### 環境需求

- Python 3.10+
- 建議安裝 CUDA（可選，用於加速推論）

### 安裝依賴

```bash
pip install flask waitress ultralytics opencv-python pillow numpy
```

### 模型檔案

請將模型放在專案根目錄：

- `yolov8n.pt`（車流偵測）
- `person_wheelchair_personWheelchairV2.pt`（行人/輪椅偵測）

### 啟動

```bash
python app.py
```

啟動後：

- 主儀表板：`http://127.0.0.1:5000`
- 演算法編輯器：`http://127.0.0.1:5001`

---

## API 端點

### 偵測相關

- `POST /detect_person`：行人/輪椅影像上傳（`application/octet-stream`）
- `POST /detect_car`：車流影像上傳
- `POST /detect_all`：相容舊版（目前導向行人流程）

### 串流與狀態

- `GET /video_feed_person`：行人串流
- `GET /video_feed_car`：車流串流
- `GET /video_feed`：相容舊版（行人串流）
- `GET /stats`：回傳系統狀態（含 `mode`、`command`、`stream_*_online`）

### 控制相關

- `POST /set_mode`：切換 `AUTO` / `MANUAL`
- `POST /manual_override`：手動送出號誌指令
- `POST /toggle_detection`：切換 AI 偵測開關
- `POST /toggle_emergency`：啟用/停用 emergency 優先功能
- `POST /toggle_wheelchair_priority`：啟用/停用輪椅自適應綠燈秒數
- `POST /trigger_emergency`：啟動 emergency 三階段狀態（`YELLOW -> ALL_RED -> HOLD`）
- `POST /clear_emergency`：清除 emergency 狀態並回復一般邏輯
- `POST /save_code`：儲存並熱重載 `logic.py`

---

### Digital Twin MVP

- `POST /digital_twin/start`：開始錄製即時交通快照（JSON 可帶 `max_frames`）
- `POST /digital_twin/stop`：停止錄製
- `POST /digital_twin/clear`：清空錄製快照
- `GET /digital_twin/session`：查詢目前錄製狀態
- `GET /digital_twin/frames`：取得原始快照資料（支援 `?limit=200`）
- `GET /digital_twin/playback`：取得時間軸回放資料（支援 `?limit=600`）
- `POST /digital_twin/compare`：What-if 策略比較（`baseline`、`pedestrian_first`、`vehicle_first`、`balanced_flow`）

---

## 用真實道路影片模擬 Car Stream

你可以在沒有 ESP32 硬體的情況下，直接用預錄道路影片回放到伺服器，讓整個系統進入可展示運行狀態。

### 1) 啟動伺服器

```bash
python app.py
```

### 2) 把影片回放成 `/detect_car` 輸入

```bash
python simulate_car_stream.py \
  --video-path ./path/to/road_video.mp4 \
  --server-url http://127.0.0.1:5000 \
  --fps 8 \
  --speed 1.0 \
  --loop
```

### 3)（建議）同步鏡像到 `/detect_person`

本專案架構中，`command/light_state` 主要由 person pipeline 更新。  
如果只送 `/detect_car`，車流與車道統計會更新，但號誌指令變化可能不明顯。

```bash
python simulate_car_stream.py \
  --video-path ./path/to/road_video.mp4 \
  --fps 8 \
  --loop \
  --mirror-to-person
```

### 4) 驗證系統是否正常運行

- Dashboard（`http://127.0.0.1:5000`）數值持續更新
- `/stats` 的 `cars`、`lane_counts`、`tidal_direction` 會變化
- 開啟 `--mirror-to-person` 時，`command` 與 `light_state` 也會持續更新

### 5) 在模擬流量上跑 Digital Twin

```bash
curl -X POST http://127.0.0.1:5000/digital_twin/start -H 'Content-Type: application/json' -d '{"max_frames":1200}'
# 讓模擬串流跑幾秒
curl -X POST http://127.0.0.1:5000/digital_twin/stop
curl -X POST http://127.0.0.1:5000/digital_twin/compare -H 'Content-Type: application/json' \
  -d '{"strategies":["baseline","pedestrian_first","vehicle_first","balanced_flow"]}'
```

備註：
- `simulate_car_stream.py` 使用與 ESP32 相同的 XOR key（`MyIoTKey2026`）與 `application/octet-stream` 傳輸格式。
- 若推論負載偏高，建議降低 `--fps` 或設定 `--resize-width`。

---

## 基本資料流

1. ESP32-CAM 擷取影像並 XOR 混淆後上傳到 Flask API。  
2. 伺服器解碼影像並執行 YOLO 推論，更新系統狀態。  
3. 行人流程依 `logic.py` 計算 `command`。  
4. Car 節點將目前 `command` 以序列格式送往 Arduino Mega。
5. Arduino Mega 依指令切換實體號誌燈。

---

## 授權

MIT License © 2026
