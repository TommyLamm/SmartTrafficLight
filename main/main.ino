#include <Arduino.h>

// ---------------------------------------------------------------------------
// main.ino（原型階段）
//
// 目的：
// 1) 讀取本地感測器訊號（壓力 + 光照）。
// 2) 從 Serial 接收 car 端回傳的交通資料。
// 3) 將潮汐方向轉換成車道箭頭顯示。
//
// 注意：
// - 此檔案目前刻意不與 ArduinoMega.ino 整合。
// - 尚未接入實際繪圖函式庫，先使用 display stub，方便先檢視
//   邏輯流程並維持可編譯的原型結構。
// ---------------------------------------------------------------------------

// 原型渲染器使用的潮汐車道顯示模式。
enum TidalLane {
  LANE_STRAIGHT,
  LANE_LEFT,
  LANE_RIGHT,
  LANE_LEFT_STRAIGHT,
  LANE_RIGHT_STRAIGHT,
  LANE_LEFT_RIGHT,
  LANE_ALL,
  LANE_X
};

// 目前車道顯示模式（由 drawLaneByDirection() 更新）。
TidalLane currentLane = LANE_STRAIGHT;

// 感測器原始讀值。
int pressure = 0;
int illuminance = 0;

// 由光照計算出的輸出亮度。
int brightness = 0;

// 壓力壅塞判斷相關計時（微秒）。
unsigned long pressureStartTime = 0UL;
unsigned long pressureTime = 0UL;
unsigned long lastJamTime = 0UL;

// 狀態旗標。
bool pressureOn = false;
bool redLight = false;
bool redLightViolation = false;
bool jam = false;
bool coolingPeriod = false;
bool failSafeMode = false;

// 從 Serial 資料解析到的最新車輛總數。
int carNum = 0;

// 從 Serial 資料解析到的最新潮汐方向。
// 期望值：LEFT_BIAS / RIGHT_BIAS / BALANCED。
String latestDirection = "BALANCED";

// ----------------------------- 可調閾值 -----------------------------
#define PRESSURE_THRESHOLD 60
#define PRESSURE_TIME_THRESHOLD_US 60000000UL
#define COOLING_TIME_US 300000000UL
#define ILLUMINANCE_UPPER_THRESHOLD 100
#define ILLUMINANCE_LOWER_THRESHOLD 40
#define CAR_NUM_THRESHOLD 10
#define WHITE 1

// ---------------------------------------------------------------------------
// Display stub（占位顯示器）
//
// 在目前原型階段，保留所有繪圖呼叫但使用 no-op 實作。
// 這樣可讓隊友先看懂渲染邏輯，同時不綁定特定 OLED 函式庫。
// ---------------------------------------------------------------------------
struct PrototypeDisplay {
  void clearDisplay() {}
  void fillRect(int, int, int, int, int) {}
  void fillTriangle(int, int, int, int, int, int, int) {}
  void display() {}
};

PrototypeDisplay display;

// 各種方向圖樣的渲染函式宣告。
void renderStraight();
void renderLeft();
void renderRight();
void renderLeftStraight();
void renderRightStraight();
void renderLeftRight();
void renderAll();
void renderX();
void drawLaneByDirection(const String& direction);
void parseSerialInput();

void setup() {
  // 原型階段使用單一 Serial：
  // - 輸入：car 流程回傳資料（若有接入）
  // - 輸出：除錯訊息
  Serial.begin(115200);
  Serial.println("main.ino prototype started");
}

void loop() {
  // 1) 先解析最新 serial 資料。
  parseSerialInput();

  // 2) 讀取本地類比感測器。
  pressure = analogRead(A0);
  illuminance = analogRead(A1);

  // 3) 壓力模組：
  //    - 判斷壓力事件開始/結束與持續時間
  //    - 搭配車數門檻推估可能壅塞
  if (pressure > PRESSURE_THRESHOLD) {
    if (!pressureOn) {
      pressureOn = true;
      pressureStartTime = micros();
      if (redLight) {
        redLightViolation = true;
      }
    }
  } else if (pressureOn) {
    // 一次壓力事件結束。
    pressureTime = micros() - pressureStartTime;
    pressureOn = false;
    if (pressureTime > PRESSURE_TIME_THRESHOLD_US && carNum > CAR_NUM_THRESHOLD) {
      jam = true;
      lastJamTime = micros();
      coolingPeriod = true;
    } else if (!coolingPeriod) {
      jam = false;
    }
  }

  // 4) 亮度模組：
  //    中間區段線性插值，兩端區段做上下限夾取。
  if (illuminance > ILLUMINANCE_UPPER_THRESHOLD) {
    brightness = 255;
  } else if (illuminance < ILLUMINANCE_LOWER_THRESHOLD) {
    brightness = 135;
  } else {
    brightness = illuminance * 2 + 55;
  }

  // 5) 車道顯示模組。
  //    若為 fail-safe，強制顯示直行。
  if (failSafeMode) {
    renderStraight();
  } else {
    drawLaneByDirection(latestDirection);
  }

  // 6) 闖紅燈抓拍預留點（後續接相機觸發）。
  if (redLightViolation) {
    redLightViolation = false;
  }

  // 7) 冷卻窗口更新。
  if (micros() - lastJamTime > COOLING_TIME_US) {
    coolingPeriod = false;
  }
  if (!redLight) {
    redLightViolation = false;
  }
}

// ---------------------------------------------------------------------------
// 解析 serial 回傳資料行
//
// 預期格式（來自 ESP32 car sketch）：
// {cars_total=12, lane_counts=(3,4,5), tidal_direction=RIGHT_BIAS, sample_window=8}
//
// 此解析器支援部分欄位：
// - 若存在 cars_total，就更新 carNum。
// - 若存在 tidal_direction，就更新 latestDirection。
// ---------------------------------------------------------------------------
void parseSerialInput() {
  if (!Serial.available()) {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (!line.length()) {
    return;
  }

  // 擷取 cars_total。
  int carsPos = line.indexOf("cars_total=");
  if (carsPos >= 0) {
    int carsValueStart = carsPos + 11;
    int carsValueEnd = line.indexOf(',', carsValueStart);
    if (carsValueEnd < 0) {
      carsValueEnd = line.length();
    }
    carNum = line.substring(carsValueStart, carsValueEnd).toInt();
  }

  // 擷取 tidal_direction。
  int dirPos = line.indexOf("tidal_direction=");
  if (dirPos >= 0) {
    int dirValueStart = dirPos + 16;
    int dirValueEnd = line.indexOf(',', dirValueStart);
    if (dirValueEnd < 0) {
      dirValueEnd = line.indexOf('}', dirValueStart);
    }
    if (dirValueEnd < 0) {
      dirValueEnd = line.length();
    }
    latestDirection = line.substring(dirValueStart, dirValueEnd);
    latestDirection.trim();
  }
}

// 將語意方向轉成具體車道模式，並呼叫對應渲染。
void drawLaneByDirection(const String& direction) {
  if (direction == "LEFT_BIAS") {
    currentLane = LANE_LEFT;
  } else if (direction == "RIGHT_BIAS") {
    currentLane = LANE_RIGHT;
  } else {
    currentLane = LANE_STRAIGHT;
  }

  switch (currentLane) {
    case LANE_STRAIGHT:
      renderStraight();
      break;
    case LANE_LEFT:
      renderLeft();
      break;
    case LANE_RIGHT:
      renderRight();
      break;
    case LANE_LEFT_STRAIGHT:
      renderLeftStraight();
      break;
    case LANE_RIGHT_STRAIGHT:
      renderRightStraight();
      break;
    case LANE_LEFT_RIGHT:
      renderLeftRight();
      break;
    case LANE_ALL:
      renderAll();
      break;
    case LANE_X:
      renderX();
      break;
  }
}


// 直行主導方向圖樣。
void renderStraight() {
  display.clearDisplay();
  display.fillRect(59, 17, 10, 42, WHITE);
  display.fillTriangle(64, 17, 51, 17, 51, 39, WHITE);
  display.fillTriangle(64, 17, 77, 17, 77, 39, WHITE);
  display.fillTriangle(64, 17, 51, 17, 64, 5, WHITE);
  display.fillTriangle(64, 17, 77, 17, 64, 5, WHITE);
  display.display();
}


// 左轉主導方向圖樣。
void renderLeft() {
  display.clearDisplay();
  display.fillRect(73, 16, 10, 40, WHITE);
  display.fillRect(57, 16, 16, 10, WHITE);
  display.fillTriangle(57, 21, 57, 34, 69, 34, WHITE);
  display.fillTriangle(57, 21, 57, 8, 69, 8, WHITE);
  display.fillTriangle(57, 21, 57, 34, 45, 21, WHITE);
  display.fillTriangle(57, 21, 57, 8, 45, 21, WHITE);
  display.display();
}


// 右轉主導方向圖樣。
void renderRight() {
  display.clearDisplay();
  display.fillRect(45, 16, 10, 40, WHITE);
  display.fillRect(55, 16, 16, 10, WHITE);
  display.fillTriangle(71, 21, 71, 34, 59, 34, WHITE);
  display.fillTriangle(71, 21, 71, 8, 59, 8, WHITE);
  display.fillTriangle(71, 21, 71, 34, 83, 21, WHITE);
  display.fillTriangle(71, 21, 71, 8, 83, 21, WHITE);
  display.display();
}


// 左轉 + 直行組合圖樣。
void renderLeftStraight() {
  display.clearDisplay();
  display.fillRect(51, 41, 20, 10, WHITE);
  display.fillTriangle(51, 46, 51, 59, 63, 59, WHITE);
  display.fillTriangle(51, 46, 51, 33, 63, 33, WHITE);
  display.fillTriangle(51, 46, 51, 59, 39, 46, WHITE);
  display.fillTriangle(51, 46, 51, 33, 39, 46, WHITE);
  display.fillRect(71, 17, 10, 42, WHITE);
  display.fillTriangle(76, 17, 63, 17, 63, 29, WHITE);
  display.fillTriangle(76, 17, 89, 17, 89, 29, WHITE);
  display.fillTriangle(76, 17, 63, 17, 76, 5, WHITE);
  display.fillTriangle(76, 17, 89, 17, 76, 5, WHITE);
  display.display();
}


// 右轉 + 直行組合圖樣。
void renderRightStraight() {
  display.clearDisplay();
  display.fillRect(57, 41, 20, 10, WHITE);
  display.fillTriangle(77, 46, 77, 59, 65, 59, WHITE);
  display.fillTriangle(77, 46, 77, 33, 65, 33, WHITE);
  display.fillTriangle(77, 46, 77, 59, 89, 46, WHITE);
  display.fillTriangle(77, 46, 77, 33, 89, 46, WHITE);
  display.fillRect(47, 17, 10, 42, WHITE);
  display.fillTriangle(52, 17, 39, 17, 39, 29, WHITE);
  display.fillTriangle(52, 17, 65, 17, 65, 29, WHITE);
  display.fillTriangle(52, 17, 39, 17, 52, 5, WHITE);
  display.fillTriangle(52, 17, 65, 17, 52, 5, WHITE);
  display.display();
}


// 左轉 + 右轉組合圖樣。
void renderLeftRight() {
  display.clearDisplay();
  display.fillRect(43, 16, 16, 10, WHITE);
  display.fillTriangle(43, 21, 43, 34, 55, 34, WHITE);
  display.fillTriangle(43, 21, 43, 8, 55, 8, WHITE);
  display.fillTriangle(43, 21, 43, 34, 31, 21, WHITE);
  display.fillTriangle(43, 21, 43, 8, 31, 21, WHITE);
  display.fillRect(59, 16, 10, 40, WHITE);
  display.fillRect(69, 16, 16, 10, WHITE);
  display.fillTriangle(85, 21, 85, 34, 73, 34, WHITE);
  display.fillTriangle(85, 21, 85, 8, 73, 8, WHITE);
  display.fillTriangle(85, 21, 85, 34, 97, 21, WHITE);
  display.fillTriangle(85, 21, 85, 8, 97, 21, WHITE);
  display.display();
}


// 全方向開放圖樣。
void renderAll() {
  display.clearDisplay();
  display.fillRect(39, 41, 20, 10, WHITE);
  display.fillTriangle(39, 46, 39, 59, 51, 59, WHITE);
  display.fillTriangle(39, 46, 39, 33, 51, 33, WHITE);
  display.fillTriangle(39, 46, 39, 59, 27, 46, WHITE);
  display.fillTriangle(39, 46, 39, 33, 27, 46, WHITE);
  display.fillRect(59, 17, 10, 42, WHITE);
  display.fillTriangle(64, 17, 51, 17, 51, 29, WHITE);
  display.fillTriangle(64, 17, 77, 17, 77, 29, WHITE);
  display.fillTriangle(64, 17, 51, 17, 64, 5, WHITE);
  display.fillTriangle(64, 17, 77, 17, 64, 5, WHITE);
  display.fillRect(69, 41, 20, 10, WHITE);
  display.fillTriangle(89, 46, 89, 59, 77, 59, WHITE);
  display.fillTriangle(89, 46, 89, 33, 77, 33, WHITE);
  display.fillTriangle(89, 46, 89, 59, 101, 46, WHITE);
  display.fillTriangle(89, 46, 89, 33, 101, 46, WHITE);
  display.display();
}


// 衝突/封鎖提示圖樣。
void renderX() {
  display.clearDisplay();
  display.fillTriangle(44, 7, 39, 12, 84, 57, WHITE);
  display.fillTriangle(44, 7, 84, 57, 89, 52, WHITE);
  display.fillTriangle(44, 57, 39, 52, 84, 7, WHITE);
  display.fillTriangle(44, 57, 84, 7, 89, 12, WHITE);
  display.display();
}
