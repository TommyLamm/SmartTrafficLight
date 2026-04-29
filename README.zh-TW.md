# Smart Traffic — AI 智慧交通號誌控制系統

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00CFFF)](https://ultralytics.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

🌐 **Language / 語言：** [English](README.md) | 繁體中文

---

本專案使用 YOLOv8 即時偵測車輛、行人與輪椅使用者，並動態決策交通號誌指令。  
系統亦包含車牌 OCR、違規擷取、車道邊界調整、Digital Twin 沙盒，以及可熱重載的 `logic.py` 演算法編輯功能。

---

## 目錄

- [系統概述](#系統概述)
- [執行預設值（程式碼核對）](#執行預設值程式碼核對)
- [硬體角色說明（Mega、ESP32-CAM、ESP8266）](#硬體角色說明megaesp32-camesp8266)
- [專案結構](#專案結構)
- [安裝與啟動](#安裝與啟動)
- [API 端點](#api-端點)
- [Digital Twin MVP](#digital-twin-mvp)
- [用真實道路影片模擬 Car Stream](#用真實道路影片模擬-car-stream)
- [基本資料流](#基本資料流)

---

## 系統概述

- **多串流 AI 偵測**
  - 車流端：`/detect_car`
  - 行人/輪椅端：`/detect_person`
  - 車牌 OCR 串流：`/detect_plate`
- **號誌控制策略**
  - 輪椅優先（依需求自適應 `PED_GREEN_10..60`）
  - 行人流量觸發短/長過街綠燈
  - 車流為主時切換 `CAR_GREEN`
  - 支援 emergency 三階段序列（`EMERGENCY_YELLOW -> EMERGENCY_ALL_RED -> EMERGENCY_RED`）
- **交通分析與營運**
  - 雙車道方向分析（`lane_counts`、`tidal_direction`）
  - 可透過 `/lane_boundaries` 調整車道分割邊界
  - 違規擷取紀錄與影像瀏覽（`/capture_violation`、`/violations`）
  - 車牌 OCR 滾動歷史（`/plates`）
- **控制模式**
  - `AUTO`：依 `logic.py` 自動決策
  - `MANUAL`：介面手動指令會鎖定保留於 `/stats`（僅允許 `CAR_GREEN` 或 `PED_GREEN_5..120`），直到下次手動覆寫或切換模式
- **熱重載**
  - 編輯 `logic.py` 後可透過 `/save_code` 即時套用，不需重啟主服務

---

## 執行預設值（程式碼核對）

- **Mega 輪詢與 failsafe 時序**
  - Mega 每 2 秒輪詢一次 `GET /stats?client=mega`（`POLL_INTERVAL_MS=2000`）
  - 若 9 秒內未收到有效 heartbeat/control packet，Mega 進入 failsafe（`FAILSAFE_TIMEOUT=9000`）
  - failsafe 下車流綠燈保底週期為 30 秒（`FAILSAFE_CAR_GREEN=30000`）
- **Digital Twin 限制**
  - `POST /digital_twin/start` 的 `max_frames` 範圍為 `60..5000`（預設 `900`）
  - 快照最小擷取間隔為 `120ms`
  - `POST /digital_twin/compare` 需要至少 15 幀錄製資料
- **Emergency 三階段時序**
  - `EMERGENCY_YELLOW`：3 秒
  - `EMERGENCY_ALL_RED`：5 秒
  - `EMERGENCY_RED` 持有：15 秒
- **手動覆寫規格**
  - `POST /manual_override` 僅在 `MANUAL` 模式可用
  - 合法指令為 `CAR_GREEN` 與 `PED_GREEN_<sec>`（`sec` 範圍 `5..120`）
- **歷史資料保留上限**
  - 車牌 OCR 歷史最多保留 50 筆（`/plates`）
  - 違規紀錄最多保留 100 筆（`/violations`）
- **Stats 回傳說明**
  - `GET /stats` 僅提供 `plates_count`，不直接回傳完整 `plates`；完整資料請使用 `GET /plates`
- **車道邊界相容鍵位**
  - `POST /lane_boundaries` 同時支援新鍵位（`boundary_top`、`boundary_bottom`）與舊鍵位（`boundary1_top`、`boundary1_bottom`）
  - 預設分割值為 `boundary_top=0.50`、`boundary_bottom=0.495`

---

## 硬體角色說明（Mega、ESP32-CAM、ESP8266）

### 1) Arduino Mega（號誌控制器）

`ArduinoMega/ArduinoMega.ino` 負責實體號誌燈狀態機與 failsafe：

- 透過 ESP8266（AT 韌體，`Serial2`）輪詢 `GET /stats?client=mega` 並解析精簡控制 payload
- 輪詢週期為 2 秒；若 9 秒未收到有效 heartbeat/control packet 會進入 failsafe
- 序列埠除錯狀態會同步後端控制模式（`[AI-Smart]` / `[MANUAL]`），且 `[Failsafe]` 仍為最高優先顯示
- 控制車道與行人 RGB 燈的狀態切換
- 由 Mega 本地讀取感測器：壓力（`A0`）、RFID（SPI，`SS=53`、`RST=49`）、照度（`A1`）
- 在 Mega 端執行 emergency / failsafe 邏輯（含 server 回到非 emergency 時的清除轉譯）
- 若超過逾時未收到有效 server 心跳/指令，進入 failsafe 循環（預設安全時序）

### 2) ESP32-CAM_Person（行人/輪椅節點）

`ESP32-CAM_Person/ESP32-CAM_Person.ino`：

- 擷取相機影像並以 XOR（`MyIoTKey2026`）混淆
- 上傳到 `POST /detect_person`
- 目前架構下不再透過 UART 直接控制 Arduino Mega

### 3) ESP32-CAM_Car（車流節點）

`ESP32-CAM_Car/ESP32-CAM_Car.ino`：

- 擷取相機影像並以同樣 XOR 方式混淆
- 上傳到 `POST /detect_car`
- 韌體支援違規擷取上傳（`/capture_violation`）
- 目前韌體已停用此節點上的壓力 / RFID 本地流程（改回 Mega）
- 不再透過 UART 轉發控制指令到 Mega

### 4) ESP8266（Mega 的 AT WiFi Bridge）

- 使用原生 AT 韌體（不需燒錄專案自訂韌體）
- 連接 Mega `Serial2`，由 `WiFiEsp` 函式庫驅動
- 提供 Mega 輪詢後端 `/stats?client=mega` 的網路通道，維持指令心跳

**Mega `/stats` 輪詢故障排除**
- 燒錄前請先在 `ArduinoMega/ArduinoMega.ino` 正確設定 `WIFI_SSID` / `WIFI_PASS`。
- 一般情況維持 `SERVER_HOST="example.com"`；只有在需要固定 IP 備援路徑時才設定 `SERVER_FALLBACK_HOST`。
- 若序列埠持續出現 `Not connected` 或 `Connect failed`，請優先檢查 ESP8266 AT 韌體、3.3V 供電穩定性，以及同一個 WiFi 下是否可連到後端 `:80`。
- 新版韌體診斷會分開顯示 link state、TCP connect、HTTP timeout、JSON parse 失敗，方便快速定位根因。

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
├── license_plate.pt
├── ArduinoMega/
│   └── ArduinoMega.ino
├── ESP32-CAM_Car/
│   └── ESP32-CAM_Car.ino
├── ESP32-CAM_Person/
│   └── ESP32-CAM_Person.ino
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

## 安裝與啟動

### 環境需求

- Python 3.10+
- 建議安裝 CUDA（可選，用於加速推論）

### 安裝依賴

```bash
pip install flask waitress ultralytics opencv-python pillow numpy requests
```

可選（車牌 OCR / 違規 OCR 功能需要）：

```bash
pip install paddleocr paddlepaddle
```

### 模型檔案

請將模型放在專案根目錄：

- `yolov8n.pt`（車流偵測）
- `person_wheelchair_personWheelchairV2.pt`（行人/輪椅偵測）
- `license_plate.pt`（車牌偵測）

### 啟動

```bash
python app.py
```

啟動後：

- 主儀表板：`http://127.0.0.1:5000`
- 演算法編輯器：`http://127.0.0.1:5001`
- 可選（儀表板 Edit 按鈕目標）：設定環境變數 `STL_EDITOR_URL`（預設：`https://example.com/`）

備註：

- `app.py` 若偵測到 `logic_editor.py`，會自動啟動編輯器。
- 若未安裝 PaddleOCR，`/detect_plate` 與 `/capture_violation` 的車牌 OCR 路徑會回傳執行期錯誤。

---

## API 端點

### 偵測相關

- `POST /detect_person`：行人/輪椅影像上傳（`application/octet-stream`）
- `POST /detect_car`：車流影像上傳
- `POST /detect_plate`：上傳影像進行車牌偵測 + OCR
- `POST /capture_violation`：上傳高解析違規快照（儲存影像與紀錄）
- `POST /capture_violation_live`：以最新車流串流畫面觸發違規擷取（不需重新上傳影像）
- `POST /detect_all`：相容舊版（目前導向行人流程）
- `GET /plates`：車牌 OCR 滾動歷史

### 串流與狀態

- `GET /video_feed_person`：行人串流
- `GET /video_feed_car`：車流串流
- `GET /stream_plate`：車牌標註 MJPEG 串流
- `GET /video_feed`：相容舊版（行人串流）
- `GET /stats`：回傳完整系統狀態（含 `mode`、`command`、`cars_total`、`lane_counts`、`tidal_direction`、`sample_window`、`stream_*_online`、`lane_boundaries`、`plates_count`、Digital Twin 旗標；完整車牌清單請改查 `/plates`）
- `GET /stats?client=mega`：Arduino Mega 輪詢用精簡 payload

### 控制相關

- `POST /set_mode`：切換 `AUTO` / `MANUAL`
- `POST /manual_override`：手動送出號誌指令（僅 `MANUAL` 可用；合法值為 `CAR_GREEN`、`PED_GREEN_5..120`）
- `POST /toggle_detection`：切換 AI 偵測開關
- `POST /toggle_emergency`：啟用/停用 emergency 優先功能（停用後 Mega 會忽略 RFID/伺服器 emergency 觸發）
- `POST /toggle_wheelchair_priority`：啟用/停用輪椅自適應綠燈秒數
- `POST /trigger_emergency`：啟動 emergency 三階段狀態（`YELLOW(3s) -> ALL_RED(5s) -> HOLD(15s)`）
- `POST /clear_emergency`：清除 emergency 狀態並回復一般邏輯
- `GET /lane_boundaries`：取得目前雙車道分割邊界（`boundary_top`、`boundary_bottom`、revision 資訊）
- `POST /lane_boundaries`：更新車道分割邊界比例
- `GET /violations`：取得違規紀錄列表
- `GET /violation_image/<filename>`：取得違規影像檔

### 編輯器相關

- `GET /get_code`：讀取目前 `logic.py`
- `POST /save_code`：儲存並熱重載 `logic.py`

---

### Digital Twin MVP

- `POST /digital_twin/start`：開始錄製即時交通快照（JSON 可帶 `max_frames`，範圍 `60..5000`，預設 `900`）
- `POST /digital_twin/stop`：停止錄製
- `POST /digital_twin/clear`：清空錄製快照
- `GET /digital_twin/session`：查詢目前錄製狀態
- `GET /digital_twin/frames`：取得原始快照資料（支援 `?limit=200`）
- `GET /digital_twin/playback`：取得時間軸回放資料（支援 `?limit=600`）
- `POST /digital_twin/compare`：What-if 策略比較（`baseline`、`pedestrian_first`、`vehicle_first`、`balanced_flow`；需至少 15 幀錄製資料）

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
- 若不希望模擬器啟動時強制切回 `AUTO`，可加上 `--keep-mode`。
- 若不希望模擬器自動開啟 detection，可加上 `--no-ensure-detection`。

---

## 基本資料流

1. ESP32-CAM（Car / Person）擷取影像並 XOR 混淆後，上傳到 Flask API。  
2. 伺服器解碼影像並執行推論，更新全域交通狀態（`command`、計數、車道資料、串流在線旗標）。  
3. 車牌與違規流程執行 YOLO + OCR，並保存滾動資料/影像（`/plates`、`/violations`）。  
4. Dashboard 可調整車道分割邊界（`boundary_top`、`boundary_bottom`）以支援雙車道分析。  
5. Arduino Mega 透過 ESP8266（AT + `WiFiEsp`）輪詢後端 `/stats?client=mega` 取得精簡控制資料。  
6. Mega 解析 `command`、`cars_total`、車道指標與 mode/emergency 旗標，更新本地狀態機上下文。  
7. Mega 執行實體號誌切換與本地感測邏輯（RFID / 壓力 / 照度 / OLED）。  
8. 若後端指令心跳中斷，Mega 進入 failsafe 安全時序。  

---

## 授權

MIT License © 2026
