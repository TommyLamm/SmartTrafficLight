INDEX_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Traffic Live Feed Dashboard</title>
        <style>
            body { 
                background-color: #0b1121; color: #94a3b8; margin: 0; padding: 2rem; 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .main-container {
                max-width: 1200px; margin: 0 auto; background-color: #171e2e; 
                padding: 20px; display: grid; grid-template-columns: 2fr 1fr; gap: 20px; 
                border-radius: 6px; border: 1px solid #1e293b; position: relative;
            }

            .panel-title { color: #38bdf8; font-size: 1.1rem; font-weight: bold; margin-bottom: 15px; }
            .video-section { padding-top: 5px; }
            .video-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px;
            }
            .camera-card {
                background-color: #27344a;
                border-radius: 6px;
                padding: 10px;
            }
            .camera-title {
                color: #cbd5e1;
                font-size: 0.95rem;
                margin-bottom: 8px;
                font-weight: 600;
            }
            .video-box {
                background-color: #334155; 
                width: 100%;
                /* Fixed aspect-ratio removed, adapts to image */
                min-height: 240px;
                border-radius: 4px; 
                display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden;
            }
            .video-box img { width: 100%; height: auto; display: block; position: relative; z-index: 2; }
            .video-box .placeholder { 
                position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                color: #94a3b8; font-size: 1.2rem; z-index: 1; 
            }

            .side-panels { display: flex; flex-direction: column; gap: 15px; }
            
            /* RWD for Mobile */
            @media (max-width: 768px) {
                body { padding: 10px; }
                .main-container { 
                    grid-template-columns: 1fr; 
                    padding: 10px;
                }
                .video-grid {
                    grid-template-columns: 1fr;
                }
                .video-box {
                    /* On mobile, auto height based on width */
                    height: auto;
                }
                .settings-button {
                    top: 15px; right: 15px;
                    padding: 8px 12px;
                }
            }

            .panel { background-color: #27344a; padding: 20px; border-radius: 6px; }
            .panel h3 { color: #5bc2fb; margin-top: 0; margin-bottom: 10px; font-size: 1rem; }
            .panel p { margin: 0; color: #cbd5e1; font-size: 0.95rem; }
            .dot { color: #4ade80; margin-right: 5px; font-size: 1.2rem; }

            /* Interactive Mode Buttons */
            .controls-row { display: flex; justify-content: space-between; gap:10px; margin-bottom: 15px; }
            .btn-mode { padding: 10px; border-radius: 4px; width: 48%; cursor: pointer; border: none; font-weight: bold; transition: 0.2s;}
            .active-auto { background-color: #4ade80; color: #064e3b; }
            .active-manual { background-color: #f87171; color: #450a0a; }
            .inactive { background-color: #334155; color: #94a3b8; border: 1px solid #475569; }
            
            /* Manual Override Commands */
            .manual-actions { display: none; gap: 10px; justify-content: space-between; }
            .btn-action { padding: 8px; border-radius: 4px; border: 1px solid #38bdf8; background: #0f172a; color: #38bdf8; cursor: pointer; width: 48%; font-weight:bold;}
            .btn-action:hover { background: #38bdf8; color: #0f172a; }

            .btn-detect-on  { background-color: #f87171; color: #450a0a; width: 100%; padding: 10px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }
            .btn-detect-off { background-color: #4ade80; color: #064e3b; width: 100%; padding: 10px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }

            ul { margin: 0; padding-left: 20px; color: #cbd5e1; font-size: 0.95rem; }
            li { margin-bottom: 5px; }

            /* ========= 新增：設定按鈕 + Editor 視窗 ========= */
            .settings-button {
                position: fixed;
                top: 10px;
                right: 10px;
                z-index: 2000;
                border: none;
                background: #333;
                color: #fff;
                border-radius: 4px;
                padding: 6px 10px;
                cursor: pointer;
                font-size: 16px;
            }

            .editor-modal {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0, 0, 0, 0.6);
                z-index: 1999;
                display: none; /* 起始隱藏 */
                align-items: center;
                justify-content: center;
            }

            .editor-modal-content {
                width: 80vw;
                height: 80vh;
                background: #1e1e1e;
                border-radius: 6px;
                box-shadow: 0 0 10px #000;
                display: flex;
                flex-direction: column;
            }

            @media (max-width: 768px) {
                .editor-modal-content {
                    width: 95vw;
                    height: 90vh;
                }
            }

            .editor-modal-header {
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 10px;
                background: #222;
                color: #fff;
                font-size: 14px;
            }

            .editor-close-btn {
                border: none;
                background: transparent;
                color: #fff;
                cursor: pointer;
                font-size: 16px;
            }
        </style>
    </head>
    <body>

        <!-- 新增：右上角設定按鈕 -->
        <button id="settings-btn" class="settings-button">⚙</button>

        <!-- 新增：Editor 彈出視窗（iframe 載入 stledit.gyke.net） -->
        <div id="editor-modal" class="editor-modal">
          <div class="editor-modal-content">
            <div class="editor-modal-header">
              <span>Algorithm Editor (logic.py)</span>
              <button id="editor-close" class="editor-close-btn">X</button>
            </div>
            <iframe
              id="editor-frame"
              data-src="https://stledit.gyke.net/"
              style="width:100%;height:100%;border:none;"
              title="Logic Editor"
            ></iframe>
          </div>
        </div>

        <div class="main-container">
            <div class="video-section">
                <div class="panel-title">Live Camera Feeds</div>
                <div class="video-grid">
                    <div class="camera-card">
                        <div class="camera-title">🚗 Car Camera</div>
                        <div class="video-box">
                            <div class="placeholder">Car Detection Stream</div>
                            <img id="streamImgCar" alt="" style="display:none;">
                        </div>
                    </div>
                    <div class="camera-card">
                        <div class="camera-title">🚶 Person/Wheelchair Camera</div>
                        <div class="video-box">
                            <div class="placeholder">Person/Wheelchair Detection Stream</div>
                            <img id="streamImgPerson" alt="" style="display:none;">
                        </div>
                    </div>
                </div>
            </div>

            <div class="side-panels">
                <div class="panel">
                    <h3>Traffic Status</h3>
                    <p>Vehicles: <span id="val-cars">0</span> | Pedestrians: <span id="val-persons">0</span></p>
                    <p>Wheelchairs: <span id="val-wheelchairs">0</span></p>
                </div>

                <div class="panel">
                    <h3>Signal Control</h3>
                    <p><span class="dot">●</span> <span id="val-state">⏳ Awaiting AI Detection...</span></p>
                </div>

                <div class="panel">
                    <h3>System Controls</h3>
                    <div class="controls-row">
                        <button id="btn-auto" class="btn-mode active-auto" onclick="setMode('AUTO')">Auto Mode</button>
                        <button id="btn-manual" class="btn-mode inactive" onclick="setMode('MANUAL')">Manual</button>
                    </div>
                    <!-- Manual Override Buttons -->
                    <div id="manual-actions" class="manual-actions">
                        <button class="btn-action" onclick="forceCommand('CAR_GREEN', this)">🚗 Force Car Green</button>
                        <button class="btn-action" onclick="forceCommand('PED_GREEN_20', this)">🚶 Force Ped Green</button>
                    </div>
                </div>

                <div class="panel">
                    <h3>Detection</h3>
                    <button id="btn-detect" class="btn-detect-on" onclick="toggleDetection()">⏹ Stop Detection</button>
                </div>

                <div class="panel">
                    <h3>Advanced Features</h3>
                    <ul>
                        <li>Emergency Priority: OFF</li>
                        <li>Pedestrian Extension: ON</li>
                    </ul>
                </div>
            </div>
        </div>

        <script>
            // Live Update
            setInterval(() => {
                fetch('/stats')
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('val-persons').innerText = data.persons;
                        document.getElementById('val-cars').innerText = data.cars;
                        document.getElementById('val-wheelchairs').innerText = data.wheelchairs || 0;
                        // Proper Mapping for UI Text
                        let uiState = "⏳ Awaiting AI Detection...";
                        if(data.light_state === "PED_WHEELCHAIR") uiState = "♿ Wheelchair Priority (Extended)";
                        else if(data.light_state === "CAR_GREEN") uiState = "🟢 Green - Vehicles (N/S)";
                        else if(data.light_state === "PED_LONG") uiState = "🚶 Pedestrian (Extended)";
                        else if(data.light_state === "PED_SHORT") uiState = "🚶 Pedestrian (Standard)";
                        else if(data.light_state === "MANUAL_OVERRIDE") {
                            uiState = "⚠️ Manual Override: " + (data.last_manual_label || "Unknown");
                        }
                        
                        document.getElementById('val-state').innerText = uiState;
                        connectStreamIfNeeded('streamImgCar', '/video_feed_car', data.stream_car_online);
                        connectStreamIfNeeded('streamImgPerson', '/video_feed_person', data.stream_person_online);

                        // Sync detection button
                        const btn = document.getElementById('btn-detect');
                        if(data.detection) {
                            btn.textContent = '⏹ Stop Detection';
                            btn.className = 'btn-detect-on';
                        } else {
                            btn.textContent = '▶ Start Detection';
                            btn.className = 'btn-detect-off';
                        }
                    })
                    .catch(err => console.error(err));
            }, 1000);

            function toggleDetection() {
                fetch('/toggle_detection', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        const btn = document.getElementById('btn-detect');
                        if(data.detection) {
                            btn.textContent = '⏹ Stop Detection';
                            btn.className = 'btn-detect-on';
                        } else {
                            btn.textContent = '▶ Start Detection';
                            btn.className = 'btn-detect-off';
                        }
                    });
            }

            // Auto / Manual System Controls Logic
            function setMode(mode) {
                fetch('/set_mode', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({mode: mode})
                }).then(() => {
                    if(mode === 'AUTO') {
                        document.getElementById('btn-auto').className = 'btn-mode active-auto';
                        document.getElementById('btn-manual').className = 'btn-mode inactive';
                        document.getElementById('manual-actions').style.display = 'none';
                    } else {
                        document.getElementById('btn-auto').className = 'btn-mode inactive';
                        document.getElementById('btn-manual').className = 'btn-mode active-manual';
                        document.getElementById('manual-actions').style.display = 'flex';
                    }
                });
            }

            function forceCommand(cmd, btn) {
                const originalText = btn.innerText;
                btn.innerText = "Sending...";
                btn.disabled = true;

                fetch('/manual_override', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({command: cmd})
                }).then(() => {
                    btn.innerText = "Sent!";
                    setTimeout(() => {
                        btn.innerText = originalText;
                        btn.disabled = false;
                    }, 1000);
                });
            }

            function connectStreamIfNeeded(imgId, streamUrl, isOnline) {
                const img = document.getElementById(imgId);
                if (!img) return;
                img.dataset.wantOnline = isOnline ? '1' : '0';

                if (isOnline) {
                    if (!img.dataset.connected || img.dataset.connected !== '1') {
                        img.dataset.connected = '1';
                        img.onload = function() {
                            this.style.display = 'block';
                        };
                        img.onerror = function() {
                            this.style.display = 'none';
                            this.dataset.connected = '0';
                            setTimeout(() => {
                                if (this.dataset.connected === '0' && this.dataset.wantOnline === '1') {
                                    this.src = streamUrl + '?' + new Date().getTime();
                                    this.dataset.connected = '1';
                                }
                            }, 2000);
                        };
                        img.src = streamUrl + '?' + new Date().getTime();
                    }
                } else {
                    if (img.dataset.connected === '1') {
                        img.removeAttribute('src');
                    }
                    img.style.display = 'none';
                    img.dataset.connected = '0';
                }
            }

            // ========= 新增：設定按鈕開關 Editor =========
            document.addEventListener('DOMContentLoaded', function () {
                connectStreamIfNeeded('streamImgCar', '/video_feed_car', false);
                connectStreamIfNeeded('streamImgPerson', '/video_feed_person', false);

                const settingsBtn = document.getElementById('settings-btn');
                const editorModal = document.getElementById('editor-modal');
                const editorClose = document.getElementById('editor-close');
                const editorFrame = document.getElementById('editor-frame');

                if (settingsBtn && editorModal && editorClose && editorFrame) {
                    settingsBtn.addEventListener('click', function () {
                        // 只在第一次打開時載入 iframe，避免每次都重新載入
                        if (!editorFrame.src && editorFrame.dataset.src) {
                            editorFrame.src = editorFrame.dataset.src;
                        }
                        editorModal.style.display = 'flex';
                    });

                    editorClose.addEventListener('click', function () {
                        editorModal.style.display = 'none';
                    });

                    editorModal.addEventListener('click', function (e) {
                        if (e.target === editorModal) {
                            editorModal.style.display = 'none';
                        }
                    });
                }
            });
        </script>
    </body>
    </html>
    """
