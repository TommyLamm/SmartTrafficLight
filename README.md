# Smart Traffic — AI 智慧交通號誌控制系統

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00CFFF)](https://ultralytics.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

以 YOLOv8 即時偵測行人、輪椅使用者與車輛，動態決策交通號誌切換時機，並提供瀏覽器內的演算法熱重載（Hot-reload）編輯器。

---

## 目錄

- [系統特色](#系統特色)
- [架構總覽](#架構總覽)
- [檔案結構](#檔案結構)
- [模組深度分析](#模組深度分析)
- [號誌決策邏輯](#號誌決策邏輯)
- [熱重載機制](#熱重載機制)
- [安裝與啟動](#安裝與啟動)
- [API 端點](#api-端點)
- [IoT 影像串流協議](#iot-影像串流協議)

---

## 系統特色

- **雙模型推論**：車輛偵測（YOLOv8n）與行人／輪椅偵測（自訓練模型）同時運行，各自獨立串流
- **輪椅優先邏輯**：偵測到輪椅使用者時自動延長行人綠燈至 30 秒
- **Zero-downtime 熱重載**：在瀏覽器直接修改號誌演算法，儲存後立即生效，無需重啟伺服器
- **AUTO / MANUAL 雙模式**：支援 AI 自動控制與操作員手動覆蓋
- **XOR 影像混淆**：IoT 裝置傳輸影像時以 XOR 加密防止明文截取
- **MJPEG 即時串流**：以 `threading.Condition` 驅動的零忙等待影像推送

---

## 架構總覽

```
┌────────────────────────────────────────┐
│            入口層  Entry               │
│   app.py          logic_editor.py      │
│  (port 5000)        (port 5001)        │
└────────────┬───────────────┬───────────┘
             │               │ 寫檔 + 通知 reload
┌────────────▼───────────────▼───────────┐
│            邏輯層  Business Logic       │
│   logic.py   core.py   config.py       │
└────────────┬───────────────────────────┘
             │
┌────────────▼───────────────────────────┐
│            服務層  Services             │
│  detect_person.py   detect_car.py      │
│  control.py   decode.py   models.py    │
│              state.py                  │
└────────────┬───────────────────────────┘
             │
┌────────────▼───────────────────────────┐
│            Web 層  Flask Blueprints     │
│  routes_detect  routes_stream          │
│  routes_controls  routes_editor        │
│  routes_ui  (ui_html.py)               │
└────────────────────────────────────────┘
```

---

## 檔案結構

```
project-root/
├── app.py                          # 主程式入口
├── logic.py                        # 號誌決策演算法（可熱重載）
├── logic_editor.py                 # 獨立編輯器伺服器（port 5001）
├── core.py                         # 對外 API 橋接門面
├── yolov8n.pt                      # 車輛偵測模型
├── person_wheelchair_personWheelchair.pt  # 預設行人／輪椅偵測模型
└── smart_traffic/
    ├── __init__.py                 # Flask Application Factory
    ├── config.py                   # 全域常數設定
    ├── models.py                   # YOLO 模型單例載入
    ├── state.py                    # 全域共享狀態倉庫
    ├── services/
    │   ├── control.py              # 號誌控制邏輯套用
    │   ├── decode.py               # XOR 影像解密
    │   ├── detect_car.py           # 車輛推論服務
    │   └── detect_person.py        # 行人／輪椅推論服務
    └── web/
        ├── __init__.py             # Blueprint 統一註冊
        ├── routes_controls.py      # 系統控制 API
        ├── routes_detect.py        # 影像上傳推論端點
        ├── routes_editor.py        # 程式碼熱重載端點
        ├── routes_stream.py        # MJPEG 影像串流
        ├── routes_ui.py            # 前端儀表板路由
        └── ui_html.py              # 儀表板 HTML 字串
```

---

## 模組深度分析

### 入口層

#### `app.py` — 主程式入口

整個系統的唯一啟動點。以 Waitress（生產等級 WSGI 伺服器，8 threads）在 port 5000 承載 Flask app；同時以 `subprocess.Popen` 在背景啟動 `logic_editor.py`（port 5001）。若找不到編輯器腳本，僅印出警告，不中斷主服務。

```python
# 關鍵片段
serve(app, host='127.0.0.1', port=5000, threads=8)
subprocess.Popen([sys.executable, 'logic_editor.py'])
```

#### `logic_editor.py` — 獨立瀏覽器編輯器

純 Python 標準函式庫（`http.server`、`ast`、`urllib`）實作的獨立 HTTP 伺服器，不依賴任何第三方套件。提供：

- 帶行號的瀏覽器內程式碼編輯器（Ctrl+S 快捷鍵儲存）
- 儲存前執行 `ast.parse()` 語法驗證，避免寫入損壞的程式碼
- 儲存後 POST 通知 Flask `/save_code` 端點觸發熱重載
- Flask 不可達時（網路錯誤）仍成功寫檔，不視為失敗

---

### 邏輯層

#### `logic.py` — 號誌決策演算法 ⭐ 核心可編輯

系統唯一的號誌決策模組，設計為**可在執行期動態替換**。函式簽名固定，內部邏輯可自由修改：

```python
def decide_light(person_count, vehicle_count, wheelchair_count, current_light_state):
    # 回傳 (command, new_light_state)
```

| 優先級 | 條件 | 發出指令 | 持續時間 |
|--------|------|----------|----------|
| 1（最高）| 偵測到輪椅使用者，車輛 ≤ 1 | `PED_GREEN_30` | 30 秒 |
| 2 | 行人 > 3，車輛 ≤ 1 | `PED_GREEN_20` | 20 秒 |
| 3 | 行人 > 0，車輛 ≤ 1 | `PED_GREEN_10` | 10 秒 |
| 4（最低）| 車輛 > 2 或無行人 | `CAR_GREEN` | — |

#### `core.py` — 公用 API 橋接門面（Facade）

對外公開的簡化介面，把內部 state、models、services 包裝成一層薄薄的代理。利用 `__getattr__` 讓 `core.sys_state` 等同 `state.sys_state`，無需重複引用。適合外部客戶端或測試腳本直接 `import core`。

#### `config.py` — 全域常數設定

集中管理所有路徑與常數，使用 `os.path.abspath` 計算絕對路徑，確保從任意工作目錄啟動皆正確：

```python
XOR_KEY              = b"MyIoTKey2026"      # IoT 傳輸混淆金鑰
STREAM_ONLINE_TTL_SEC = 5.0                  # 串流存活判斷門檻（秒）
CAR_TARGET_CLASSES   = [2, 3, 5, 7]         # COCO 車輛類別 ID
```

---

### 狀態層

#### `state.py` — 全域共享狀態倉庫

全系統唯一的可變狀態中心，所有執行緒共用。包含：

- `sys_state`：字典，存放即時的人、車、輪椅計數、燈號狀態、運作模式
- `infer_lock`（`threading.Lock`）：確保車輛與行人推論不同時佔用模型
- `frame_condition_person` / `frame_condition_car`（`threading.Condition`）：讓 MJPEG 串流以事件通知驅動，避免忙等待（busy-wait）

```python
sys_state = {
    "persons": 0, "cars": 0, "wheelchairs": 0,
    "command": "KEEP", "light_state": "UNKNOWN",
    "mode": "AUTO",   # "AUTO" | "MANUAL"
    "detection": True
}
```

> ⚠️ **不可熱重載**：reload 此模組會重建執行緒鎖與狀態字典，導致全系統狀態遺失與執行緒死鎖。

---

### 服務層

#### `models.py` — YOLO 模型單例

在模組首次 import 時即載入兩個模型（單例模式），整個應用程式共用，避免重複佔用 GPU 記憶體：

```python
car_model    = YOLO(CAR_MODEL_PATH)                      # 車輛偵測
person_model = YOLO(PERSON_MODEL_PATH)                   # 行人 / 輪椅偵測
```

> ⚠️ **不可熱重載**：重新載入模型需數秒且舊實例不會釋放，造成記憶體洩漏。

#### `decode.py` — XOR 影像解密

使用 NumPy 向量化運算高效還原 IoT 裝置傳來的混淆影像：

```python
key_arr      = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(input_arr))
decrypted    = np.bitwise_xor(input_arr, key_arr).tobytes()
image        = Image.open(io.BytesIO(decrypted))
```

金鑰長度 12 bytes，以 `np.resize` 循環填充至影像長度，解密後直接轉為 PIL Image。

#### `detect_person.py` — 行人／輪椅推論服務

接收加密影像 → 解密 → YOLOv8 推論（imgsz=640）→ 標籤正規化分類 → 更新 state → 寫入 MJPEG 幀緩衝 → 觸發控制邏輯。

標籤正規化（去除大小寫、特殊字元）確保模型輸出相容性：

```python
def normalize_label(label):
    return "".join(ch for ch in str(label).lower() if ch.isalnum())
# "PersonWheelchair" -> "personwheelchair" -> 計入輪椅優先
# "wheelchair"（空輪椅）-> 不計入優先計數
```

#### `detect_car.py` — 車輛推論服務

流程與 `detect_person.py` 相同，但使用較高解析度（imgsz=800）以提升遠距車輛偵測精度。車輛計數只更新 `sys_state["cars"]`，**不觸發號誌邏輯**（號誌統一由行人端觸發，避免競態）。

#### `control.py` — 號誌控制邏輯套用

根據目前模式決定行為：

```
AUTO 模式  → 呼叫 logic.decide_light() → 更新 command 與 light_state
MANUAL 模式 → 消費 manual_override（一次性）→ 更新 command
           → 若無 override → 回傳 KEEP
```

---

### Web 層（Flask Blueprints）

#### `routes_detect.py`

| 端點 | 方法 | 說明 |
|------|------|------|
| `/detect_all` | POST | 行人推論（向下相容別名） |
| `/detect_person` | POST | 行人／輪椅推論 |
| `/detect_car` | POST | 車輛推論 |

Request body 為 XOR 加密的原始 JPEG 位元組。

#### `routes_stream.py`

以 `multipart/x-mixed-replace` 協議推送 MJPEG 影像串流。`threading.Condition.wait()` 阻塞直到有新幀，確保零 CPU 閒置輪詢：

| 端點 | 串流內容 |
|------|----------|
| `/video_feed` | 行人偵測標注影像（向下相容） |
| `/video_feed_person` | 行人偵測標注影像 |
| `/video_feed_car` | 車輛偵測標注影像 |

#### `routes_controls.py`

| 端點 | 方法 | 說明 |
|------|------|------|
| `/stats` | GET | 回傳完整系統狀態（含串流在線狀態） |
| `/set_mode` | POST | 切換 AUTO / MANUAL |
| `/manual_override` | POST | 送出手動燈號指令 |
| `/toggle_detection` | POST | 開關 AI 偵測 |

#### `routes_editor.py`

Flask 端的熱重載接收者。`/save_code` 收到程式碼後先做語法驗證，成功才寫檔，最後執行 `importlib.reload(logic)` 讓新演算法即時生效：

```python
ast.parse(new_code)           # 語法錯誤 → 拒絕寫入
with open(LOGIC_PATH, 'w', encoding='utf-8') as f:
    f.write(new_code)
importlib.reload(logic)       # 熱重載，無需重啟
```

#### `routes_ui.py` + `ui_html.py`

前端儀表板以字串形式內嵌於 `ui_html.py`，`render_template_string` 直接渲染，無需模板資料夾，便於單目錄打包部署。

---

## 號誌決策邏輯

```
IoT 攝影機（行人端）
    │
    ▼ XOR 解密
    ▼ YOLOv8 推論
    ▼ 標籤正規化
    ├── person_count  ──┐
    └── wheelchair_count ──┤
                         ▼
                    control.py
                         │
              ┌──────────┴──────────┐
           AUTO 模式            MANUAL 模式
              │                    │
       logic.decide_light()   manual_override
              │                    │
              └──────────┬─────────┘
                         ▼
                  sys_state["command"]
                         │
              ┌──────────▼──────────┐
           PED_GREEN_30       CAR_GREEN
           PED_GREEN_20         KEEP
           PED_GREEN_10
```

---

## 熱重載機制

系統提供「雙保險」熱重載路徑，確保在網路故障時仍可正常更新演算法：

```
瀏覽器（port 5001）
    │
    ├─ 1. 語法驗證（ast.parse）
    ├─ 2. 寫入 logic.py
    └─ 3. POST /save_code → Flask（port 5000）
                                │
                                ├─ 語法驗證（再次）
                                ├─ 寫入 logic.py
                                └─ importlib.reload(logic) ✓
```

若步驟 3 的網路請求失敗，檔案仍已寫入磁碟。Flask 下次收到推論請求時，`logic` 模組仍為舊版本，但可透過 `/save_code` 端點補發通知。

### 各模組熱重載可行性

| 模組 | 熱重載 | 說明 |
|------|--------|------|
| `logic.py` | ✅ 完整支援 | 已內建，儲存即生效 |
| `ui_html.py` | ⚠️ 需小改 | `routes_ui.py` 須改為模組級動態存取 |
| `control.py` | ⚠️ 謹慎 | 需連帶 reload `detect_person.py` |
| `detect_person.py` | ⚠️ 謹慎 | 建議停偵測後再操作 |
| `state.py` | ❌ 禁止 | 重建執行緒鎖導致死鎖 |
| `models.py` | ❌ 禁止 | 重載模型造成記憶體洩漏 |
| `config.py` | ❌ 無效 | 常數已被各模組複製，reload 無影響 |

---

## 安裝與啟動

### 環境需求

- Python 3.10+
- CUDA（選用，推薦用於推論加速）

### 安裝依賴

```bash
pip install flask waitress ultralytics opencv-python pillow numpy
```

### 放置模型檔案

```
project-root/
├── yolov8n.pt                           # 從 Ultralytics 下載
└── person_wheelchair_personWheelchair.pt  # 自訓練模型
```

### 啟動

```bash
python app.py
```

| 服務 | 網址 |
|------|------|
| 主儀表板 | http://127.0.0.1:5000 |
| 演算法編輯器 | http://127.0.0.1:5001 |

---

## API 端點

### 影像上傳推論

```http
POST /detect_person
Content-Type: application/octet-stream

<XOR 加密的 JPEG 位元組>
```

回應：

```json
{
  "persons": 2,
  "cars": 1,
  "wheelchairs": 0,
  "command": "PED_GREEN_10"
}
```

### 系統狀態查詢

```http
GET /stats
```

回應：

```json
{
  "persons": 2,
  "cars": 1,
  "wheelchairs": 0,
  "command": "PED_GREEN_10",
  "light_state": "PED_SHORT",
  "mode": "AUTO",
  "detection": true,
  "stream_car_online": true,
  "stream_person_online": true
}
```

### 模式切換

```http
POST /set_mode
Content-Type: application/json

{"mode": "MANUAL"}
```

### 手動覆蓋

```http
POST /manual_override
Content-Type: application/json

{"command": "CAR_GREEN"}
```

內建 UI 提供指令：`CAR_GREEN`、`PED_GREEN_20`  
（API 目前未限制字串內容，建議僅使用上述指令）

---

## IoT 影像串流協議

IoT 端裝置（攝影機節點）以固定頻率擷取影像後，使用 XOR 混淆後 POST 至伺服器：

```python
import numpy as np
import requests

XOR_KEY = b"MyIoTKey2026"

def obfuscate(jpeg_bytes: bytes) -> bytes:
    arr     = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    key_arr = np.resize(np.frombuffer(XOR_KEY, dtype=np.uint8), len(arr))
    return np.bitwise_xor(arr, key_arr).tobytes()

# 上傳
requests.post("http://<server>:5000/detect_person",
              data=obfuscate(jpeg_bytes),
              headers={"Content-Type": "application/octet-stream"})
```

---

## 授權

MIT License © 2026
