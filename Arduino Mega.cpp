// Car RGB pins
#define CAR_RED_PIN 2
#define CAR_GREEN_PIN 3
#define CAR_BLUE_PIN 4

// Ped RGB pins
#define PED_RED_PIN 5
#define PED_GREEN_PIN 6
#define PED_BLUE_PIN 7

enum TrafficState {
  STATE_CAR_GREEN, STATE_CAR_YELLOW, STATE_PED_GREEN, STATE_PED_BLINK, STATE_PED_RED_WAIT
};

TrafficState currentState = STATE_CAR_GREEN;
unsigned long stateStartTime = 0;
unsigned long pedGreenDuration = 15000;

unsigned long lastHeartbeatTime = 0;
const unsigned long FAILSAFE_TIMEOUT = 5000; // 測試用5秒
bool failSafeMode = true; 

unsigned long lastLogTime = 0;

void setup() {
  Serial.begin(115200);   // 電腦
  Serial1.begin(115200);  // 接收 ESP32 (TX0)
  
  pinMode(CAR_RED_PIN, OUTPUT);
  pinMode(CAR_GREEN_PIN, OUTPUT);
  pinMode(CAR_BLUE_PIN, OUTPUT);
  pinMode(PED_RED_PIN, OUTPUT);
  pinMode(PED_GREEN_PIN, OUTPUT);
  pinMode(PED_BLUE_PIN, OUTPUT);

  switchState(STATE_CAR_GREEN);
  Serial.println("=== STL Mega System Started (Parsing [CMD]) ===");
}

void loop() {
  // ===============================================
  // 1. 智慧讀取邏輯 (尋找 [] 包裹的指令)
  // ===============================================
  if (Serial1.available() > 0) {
    char c = Serial1.read();
    
    // 只有偵測到 '[' 才開始認真讀取
    if (c == '[') {
      // 讀取直到遇到 ']'
      String cmd = Serial1.readStringUntil(']');
      cmd.trim(); 
      
      // 確認指令有效性
      if (cmd.length() > 0) {
        lastHeartbeatTime = millis();
        
        if (failSafeMode) {
          Serial.print(">> [SYSTEM] 收到有效指令 [");
          Serial.print(cmd);
          Serial.println("]！AI 模式啟動。");
          failSafeMode = false;
        }

        // 執行指令
        if (cmd == "CAR_GREEN") {
          if (currentState != STATE_CAR_GREEN && currentState != STATE_CAR_YELLOW) {
             Serial.println(">> [CMD] 插隊：切換車道綠燈");
             switchState(STATE_PED_BLINK); 
          }
        } 
        else if (cmd == "PED_GREEN_10") {
          Serial.println(">> [CMD] 請求行人過馬路 (10秒)");
          requestPedestrianCrossing(10000); 
        } 
        else if (cmd == "PED_GREEN_20") {
          Serial.println(">> [CMD] 請求行人過馬路 (20秒)");
          requestPedestrianCrossing(20000); 
        }   
        else if (cmd == "PED_GREEN_30") {
          Serial.println(">> [CMD] 輪椅使用者過馬路 (30秒優先)");
          requestPedestrianCrossing(30000);
        }
        else if (cmd == "KEEP") {
          // 純心跳包，什麼都不做
        }
      }
    }
    // 如果收到的不是 '[' (例如 Wi-Fi 連線訊息)，直接忽略丟棄
  }

  // ===============================================
  // 2. 檢查斷線
  // ===============================================
  if (!failSafeMode && (millis() - lastHeartbeatTime > FAILSAFE_TIMEOUT)) {
    Serial.println("!! [WARNING] 伺服器失聯！啟動 Failsafe !!");
    failSafeMode = true; 
  }

  // ===============================================
  // 3. 狀態機邏輯 (保持不變)
  // ===============================================
  unsigned long currentTime = millis();
  unsigned long timeInState = currentTime - stateStartTime;

  switch (currentState) {
    case STATE_CAR_GREEN:
      setLights(0, 1, 0,  1, 0, 0); 
      if (failSafeMode && timeInState > 30000) {
        pedGreenDuration = 15000; 
        switchState(STATE_CAR_YELLOW);
      }
      break;

    case STATE_CAR_YELLOW:
      setLights(1, 1, 0,  1, 0, 0); 
      if (timeInState > 3000) switchState(STATE_PED_GREEN);
      break;

    case STATE_PED_GREEN:
      setLights(1, 0, 0,  0, 1, 0); 
      if (timeInState > pedGreenDuration) switchState(STATE_PED_BLINK);
      break;

    case STATE_PED_BLINK:
      if ((timeInState / 500) % 2 == 0) setLights(1, 0, 0,  0, 1, 0); 
      else setLights(1, 0, 0,  0, 0, 0); 
      if (timeInState > 4000) switchState(STATE_PED_RED_WAIT);
      break;

    case STATE_PED_RED_WAIT:
      setLights(1, 0, 0,  1, 0, 0); 
      if (timeInState > 2000) switchState(STATE_CAR_GREEN);
      break;
  }

  // 狀態輸出
  if (currentTime - lastLogTime >= 1000) {
    lastLogTime = currentTime;
    printSystemStatus(timeInState);
  }
}

void requestPedestrianCrossing(unsigned long duration) {
  if (currentState == STATE_CAR_GREEN) {
    pedGreenDuration = duration;
    switchState(STATE_CAR_YELLOW);
  }
}

void switchState(TrafficState newState) {
  currentState = newState;
  stateStartTime = millis();
  printSystemStatus(0);
}

void setLights(int cr, int cg, int cb, int pr, int pg, int pb) {
  digitalWrite(CAR_RED_PIN, cr ? HIGH : LOW);
  digitalWrite(CAR_GREEN_PIN, cg ? HIGH : LOW);
  digitalWrite(CAR_BLUE_PIN, cb ? HIGH : LOW);
  digitalWrite(PED_RED_PIN, pr ? HIGH : LOW);
  digitalWrite(PED_GREEN_PIN, pg ? HIGH : LOW);
  digitalWrite(PED_BLUE_PIN, pb ? HIGH : LOW);
}

void printSystemStatus(unsigned long timeInState) {
  String modeStr = failSafeMode ? "[Failsafe]" : "[AI-Smart]";
  String lightStr = "";
  long remainingSeconds = 0;

  switch (currentState) {
    case STATE_CAR_GREEN:
      lightStr = "車:綠 | 人:紅";
      if (failSafeMode) remainingSeconds = (30000 - timeInState) / 1000;
      else remainingSeconds = -1;
      break;
    case STATE_CAR_YELLOW:
      lightStr = "車:黃 | 人:紅";
      remainingSeconds = (3000 - timeInState) / 1000;
      break;
    case STATE_PED_GREEN:
      lightStr = "車:紅 | 人:綠";
      remainingSeconds = (pedGreenDuration - timeInState) / 1000;
      break;
    case STATE_PED_BLINK:
      lightStr = "車:紅 | 人:閃";
      remainingSeconds = (4000 - timeInState) / 1000;
      break;
    case STATE_PED_RED_WAIT:
      lightStr = "車:全紅 | 人:全紅";
      remainingSeconds = (2000 - timeInState) / 1000;
      break;
  }

  String timeStr = (remainingSeconds < 0) ? "等待指令..." : String(remainingSeconds) + "s";
  Serial.print(modeStr); Serial.print(" ");
  Serial.print(lightStr); Serial.print(" >> ");
  Serial.println(timeStr);
}
