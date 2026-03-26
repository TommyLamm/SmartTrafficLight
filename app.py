import os
import ast  
import importlib
from flask import Flask, request, jsonify, Response, render_template_string
import core  

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGIC_PATH = os.path.join(BASE_DIR, 'logic.py')

# ---------------- API ENDPOINTS ----------------
@app.route('/detect_all', methods=['POST'])
def detect_all():
    try:
        if not request.data: return jsonify({"error": "No Data"}), 400
        return jsonify(core.process_traffic_data(request.data)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def generate_frames():
    while True:
        with core.frame_condition:
            core.frame_condition.wait()
            frame = core.latest_frame
        if frame is not None:
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stats')
def stats():
    return jsonify(core.sys_state)

# ---------------- SYSTEM CONTROLS ----------------
@app.route('/set_mode', methods=['POST'])
def set_mode():
    mode = request.json.get("mode")
    if mode in["AUTO", "MANUAL"]:
        core.sys_state["mode"] = mode
    return jsonify({"success": True, "mode": core.sys_state["mode"]})

@app.route('/manual_override', methods=['POST'])
def manual_override():
    if core.sys_state["mode"] == "MANUAL":
        core.sys_state["manual_override"] = request.json.get("command")
    return jsonify({"success": True})

@app.route('/toggle_detection', methods=['POST'])
def toggle_detection():
    core.sys_state["detection"] = not core.sys_state["detection"]
    return jsonify({"success": True, "detection": core.sys_state["detection"]})

# ---------------- CODE EDITOR (HOT RELOAD) ----------------
@app.route('/get_code')
def get_code():
    try:
        with open(LOGIC_PATH, 'r', encoding='utf-8') as f: return f.read()
    except Exception as e:
        return f"File Error: {str(e)}", 500

@app.route('/save_code', methods=['POST'])
def save_code():
    new_code = request.form.get("code")
    try:
        ast.parse(new_code) # Pre-flight Syntax Check
    except SyntaxError as e:
        return jsonify({"success": False, "error": f"Line {e.lineno}: {e.msg}\nSnippet: {e.text}"}), 400

    try:
        # Save file
        with open(LOGIC_PATH, 'w', encoding='utf-8') as f:
            f.write(new_code)
        
        # 🔥 INSTANT HOT RELOAD: Updates AI logic without crashing/restarting the server!
        importlib.reload(core.logic) 
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
@app.route('/editor')
def editor_ui():
    """內嵌 code editor，取代外部 iframe"""
    try:
        with open(LOGIC_PATH, 'r', encoding='utf-8') as f:
            code = f.read()
    except:
        code = "# logic.py not found"
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Algorithm Editor</title>
    <style>
        body {{ background: #1e1e1e; color: #fff; font-family: monospace; padding: 20px; }}
        #editor {{ width: 100%; height: 80vh; background: #0d1117; color: #c9d1d9; 
                  border: none; padding: 10px; font-size: 14px; font-family: monospace; }}
        .toolbar {{ margin-bottom: 10px; }}
        button {{ background: #238636; color: white; border: none; padding: 8px 16px; 
                 border-radius: 6px; cursor: pointer; margin-right: 10px; }}
        button:hover {{ background: #2ea043; }}
        .status {{ color: #58a6ff; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="toolbar">
        <button onclick="saveCode()">💾 Save & Reload</button>
        <span class="status" id="status">Ready</span>
    </div>
    <textarea id="editor">{code}</textarea>
    
    <script>
        function saveCode() {{
            const code = document.getElementById('editor').value;
            document.getElementById('status').textContent = 'Saving...';
            
            fetch('/save_code', {{
                method: 'POST',
                body: new URLSearchParams({{'code': code}})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    document.getElementById('status').textContent = '✅ Saved & Reloaded!';
                    document.getElementById('status').style.color = '#58a6ff';
                }} else {{
                    document.getElementById('status').textContent = '❌ ' + data.error;
                    document.getElementById('status').style.color = '#f85149';
                }}
            }});
        }}
        
        // Ctrl+S 快速儲存
        document.addEventListener('keydown', (e) => {{
            if (e.ctrlKey && e.key === 's') {{
                e.preventDefault();
                saveCode();
            }}
        }});
    </script>
</body>
</html>
    """
    return html


# ---------------- WEB UI ----------------
@app.route('/')
def index():
    html = """
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
            .video-box {
                background-color: #334155; height: 500px; border-radius: 4px; 
                display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden;
            }
            .video-box img { width: 100%; height: 100%; object-fit: cover; position: absolute; z-index: 2; }
            .video-box .placeholder { color: #94a3b8; font-size: 1.2rem; z-index: 1; }

            .side-panels { display: flex; flex-direction: column; gap: 15px; }
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
              src="http://stledit.gyke.net/"
              style="width:100%;height:100%;border:none;"
              title="Logic Editor"
            ></iframe>
          </div>
        </div>

        <div class="main-container">
            <div class="video-section">
                <div class="panel-title">Live Camera Feed</div>
                <div class="video-box">
                    <div class="placeholder">Real-time YOLO Detection</div>
                    <img id="streamImg" src="/video_feed" alt="" onerror="this.style.display='none'" onload="this.style.display='block'">
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
                        <button class="btn-action" onclick="forceCommand('CAR_GREEN')">🚗 Force Car Green</button>
                        <button class="btn-action" onclick="forceCommand('PED_GREEN_20')">🚶 Force Ped Green</button>
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
                        else if(data.light_state === "MANUAL_OVERRIDE") uiState = "⚠️ Manual Override Sent";
                        
                        document.getElementById('val-state').innerText = uiState;

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

            function forceCommand(cmd) {
                fetch('/manual_override', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({command: cmd})
                });
            }

            // Image stream reconnection
            const img = document.getElementById('streamImg');
            img.onerror = function() {
                this.style.display='none';
                setTimeout(() => { img.src = '/video_feed?' + new Date().getTime(); }, 2000);
            };

            // ========= 新增：設定按鈕開關 Editor =========
            document.addEventListener('DOMContentLoaded', function () {
                const settingsBtn = document.getElementById('settings-btn');
                const editorModal = document.getElementById('editor-modal');
                const editorClose = document.getElementById('editor-close');

                if (settingsBtn && editorModal && editorClose) {
                    settingsBtn.addEventListener('click', function () {
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
    return render_template_string(html)

if __name__ == '__main__':
    import subprocess
    import sys

    editor_path = os.path.join(BASE_DIR, 'logic_editor.py')
    if os.path.exists(editor_path):
        subprocess.Popen([sys.executable, editor_path])
        print("📝 Algorithm Editor  - Open http://127.0.0.1:5001")
    else:
        print("⚠️  logic_editor.py not found — editor will not start.")

    from waitress import serve
    print("🚀 App Running       - Open http://127.0.0.1:5000")
    serve(app, host='127.0.0.1', port=5000, threads=8)
