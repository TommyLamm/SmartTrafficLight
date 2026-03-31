# Arduino Mega 正式燒錄前 Checklist

此文件對應檔案：`ArduinoMega.ino`  
目的：在**正式燒錄前**，確保設定、編譯與硬體條件都正確，避免上板後才發現問題。


## 1) 先替換 RFID UID（必要）

在 `ArduinoMega.ino` 中找到以下巨集，改成你的真實 emergency 卡 UID：

```cpp
#define EMERGENCY_UID_1_B0 ...
#define EMERGENCY_UID_1_B1 ...
#define EMERGENCY_UID_1_B2 ...
#define EMERGENCY_UID_1_B3 ...

#define EMERGENCY_UID_2_B0 ...
#define EMERGENCY_UID_2_B1 ...
#define EMERGENCY_UID_2_B2 ...
#define EMERGENCY_UID_2_B3 ...
```

> 注意：目前檔案內預設值是範例值，不可直接用於正式燒錄。


## 2) 保持 UID Gate 開啟（建議正式環境必開）

確認：

```cpp
#define ENFORCE_RFID_UID_GATE 1
```

意義：若你還沒替換範例 UID，編譯會被 `#error` 擋下，避免錯誤韌體被燒進板子。


## 3) 依硬體接線決定功能開關

在 `ArduinoMega.ino` 檔頭確認這三個旗標：

```cpp
#define ENABLE_RFID 1
#define ENABLE_OLED 1
#define ENFORCE_RFID_UID_GATE 1
```

建議：

- RFID 還沒接好：先設 `ENABLE_RFID 0`
- OLED 還沒接好：先設 `ENABLE_OLED 0`
- 正式版要用 RFID：`ENABLE_RFID 1` 且 UID 必須是實值


## 4) 確認腳位與接線（本合併版本固定用 22-27）

此版本 LED 腳位為：

- Car RGB: `22, 23, 24`
- Ped RGB: `25, 26, 27`

請確認你的實體線路與此一致。  
若你硬體仍是舊版 2-7，請先改線或改碼再燒錄。


## 5) 編譯檢查（燒錄前必做）

### 5.1 正式檢查（Gate 開啟）

應該要能通過；若 UID 還是範例值，這一步會失敗（這是預期保護機制）。

```powershell
C:\Path-to\arduino-cli.exe compile --fqbn arduino:avr:mega C:\Path-to\ArduinoMega.ino
```

### 5.2 僅除錯時臨時關 Gate（非正式）

只用於確認程式本體可編譯，不可當正式流程終點：

```powershell
C:\Path-to\arduino-cli.exe compile --fqbn arduino:avr:mega --build-property "build.extra_flags=-DENFORCE_RFID_UID_GATE=0" C:\Path-to\ArduinoMega.ino
```


## 6) 上板前最後確認

- `EMERGENCY_UID_*` 已全部替換成真實 UID
- `ENFORCE_RFID_UID_GATE = 1`
- 功能旗標符合實際接線（RFID/OLED）
- LED 腳位接線確認為 `22-27`
- 編譯成功（不依賴關 gate）


## 7) 燒錄後最小煙霧測試（建議）

1. 開序列監控（115200）。  
2. 觀察啟動日誌有無異常。  
3. 發送 `[KEEP]`、`[PED_GREEN_10]`、`[CAR_GREEN]` 確認狀態機可切換。  
4. 若 RFID 開啟，用 emergency 卡驗證是否進入 `STATE_EMERGENCY`。  
5. 若壓力感測器已接，確認紅燈壓下時會送出 `[VIOLATION]`。
