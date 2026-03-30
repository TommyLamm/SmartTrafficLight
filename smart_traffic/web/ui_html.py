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
                min-height: 240px;
                border-radius: 4px; 
                display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden;
            }
            .video-box img { width: 100%; height: auto; display: block; position: relative; z-index: 2; }
            .video-box .placeholder { 
                position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                color: #94a3b8; font-size: 1.2rem; z-index: 1; 
            }
            .video-box.car-lane-overlay .lane-overlay {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 3;
                pointer-events: none;
            }
            .video-box.car-lane-overlay .lane-overlay line {
                width: 2px;
                stroke-width: 2.5;
                filter: drop-shadow(0px 0px 3px rgba(0,0,0,0.8));
            }
            #laneLine1 { stroke: #38bdf8; }
            #laneLine2 { stroke: #f43f5e; }
            .lane-tuning-container {
                margin-top: 15px;
                background-color: rgba(15, 23, 42, 0.4);
                border-radius: 6px;
                padding: 12px;
                border: 1px solid #334155;
            }
            .lane-tuning-header {
                color: #e2e8f0;
                font-size: 0.85rem;
                font-weight: 600;
                display: flex;
                align-items: center;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                cursor: pointer;
                user-select: none;
                list-style: none;
                outline: none;
            }
            .lane-tuning-header::-webkit-details-marker { display: none; }
            details[open] > .lane-tuning-header { margin-bottom: 15px; }
            .lane-tuning-header::before {
                content: "⛕";
                margin-right: 8px;
                font-size: 1.1rem;
                color: #38bdf8;
            }
            .lane-tuning-header::after {
                content: "▼";
                margin-left: auto;
                font-size: 0.7rem;
                color: #94a3b8;
                transition: transform 0.2s ease;
            }
            details:not([open]) > .lane-tuning-header::after { transform: rotate(-90deg); }
            .lane-slider-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
            .lane-slider-col { display: flex; flex-direction: column; }
            .lane-slider-title { font-size: 0.8rem; font-weight: bold; margin-bottom: 8px; }
            .lane-slider-item { display: flex; flex-direction: column; gap: 5px; }
            .lane-slider-head { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: #94a3b8; font-weight: 500;}
            .lane-slider-head span:last-child { color: #f8fafc; font-variant-numeric: tabular-nums; background: #334155; padding: 2px 6px; border-radius: 4px;}
            .lane-slider-item input[type="range"] { width: 100%; margin: 0; }
            .left-boundary-slider input[type="range"] { accent-color: #38bdf8; }
            .right-boundary-slider input[type="range"] { accent-color: #f43f5e; }
            .lane-boundary-status { margin-top: 12px; font-size: 0.75rem; color: #94a3b8; min-height: 1.2em; text-align: right;}

            .side-panels { display: flex; flex-direction: column; gap: 15px; }

            /* ===== VIOLATIONS PANEL ===== */
            .violations-section {
                margin-top: 20px;
            }
            .violations-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 12px;
            }
            .violations-header .panel-title {
                margin-bottom: 0;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .violations-badge {
                background: #dc2626;
                color: #fff;
                font-size: 0.7rem;
                font-weight: 700;
                border-radius: 999px;
                padding: 2px 8px;
                min-width: 22px;
                text-align: center;
                line-height: 1.5;
                letter-spacing: 0.02em;
            }
            .violations-clear-btn {
                background: transparent;
                border: 1px solid #475569;
                color: #94a3b8;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 0.75rem;
                cursor: pointer;
                transition: 0.15s;
            }
            .violations-clear-btn:hover { border-color: #f87171; color: #f87171; }

            .violations-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                gap: 12px;
            }
            .violation-card {
                background: #1e2d45;
                border: 1px solid #2d3f59;
                border-radius: 6px;
                overflow: hidden;
                cursor: pointer;
                transition: border-color 0.15s, box-shadow 0.15s;
                position: relative;
            }
            .violation-card:hover {
                border-color: #f43f5e;
                box-shadow: 0 0 0 1px #f43f5e40, 0 4px 16px #0005;
            }
            .violation-thumb {
                width: 100%;
                aspect-ratio: 16/9;
                object-fit: cover;
                display: block;
                background: #0f172a;
            }
            .violation-thumb-placeholder {
                width: 100%;
                aspect-ratio: 16/9;
                background: #0f172a;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #475569;
                font-size: 1.6rem;
            }
            .violation-info {
                padding: 8px 10px;
            }
            .violation-time {
                font-size: 0.72rem;
                color: #64748b;
                margin-bottom: 2px;
                font-variant-numeric: tabular-nums;
            }
            .violation-vehicles {
                font-size: 0.8rem;
                color: #cbd5e1;
                font-weight: 600;
            }
            .violation-new-badge {
                position: absolute;
                top: 6px;
                right: 6px;
                background: #dc2626;
                color: #fff;
                font-size: 0.6rem;
                font-weight: 700;
                border-radius: 3px;
                padding: 1px 5px;
                letter-spacing: 0.05em;
                text-transform: uppercase;
            }
            .violations-empty {
                grid-column: 1 / -1;
                text-align: center;
                color: #475569;
                padding: 32px 0;
                font-size: 0.9rem;
            }
            .violations-empty .empty-icon { font-size: 2rem; margin-bottom: 8px; }

            /* ===== LIGHTBOX ===== */
            .lightbox-overlay {
                display: none;
                position: fixed;
                inset: 0;
                background: rgba(0,0,0,0.85);
                z-index: 3000;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                padding: 20px;
            }
            .lightbox-overlay.open { display: flex; }
            .lightbox-img-wrap {
                position: relative;
                max-width: 90vw;
                max-height: 80vh;
            }
            .lightbox-img-wrap img {
                max-width: 90vw;
                max-height: 75vh;
                border-radius: 6px;
                box-shadow: 0 0 60px #000a;
                display: block;
            }
            .lightbox-close {
                position: absolute;
                top: -36px;
                right: 0;
                background: transparent;
                border: none;
                color: #fff;
                font-size: 1.5rem;
                cursor: pointer;
                opacity: 0.8;
            }
            .lightbox-close:hover { opacity: 1; }
            .lightbox-meta {
                margin-top: 12px;
                text-align: center;
                color: #94a3b8;
                font-size: 0.85rem;
            }
            .lightbox-meta strong { color: #f43f5e; }

            /* RWD */
            @media (max-width: 768px) {
                body { padding: 10px; }
                .main-container { grid-template-columns: 1fr; padding: 10px; }
                .video-grid { grid-template-columns: 1fr; }
                .lane-slider-grid { grid-template-columns: 1fr; }
                .violations-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
                .settings-button { top: 15px; right: 15px; padding: 8px 12px; }
            }

            .panel { background-color: #27344a; padding: 20px; border-radius: 6px; }
            .panel h3 { color: #5bc2fb; margin-top: 0; margin-bottom: 10px; font-size: 1rem; }
            .panel p { margin: 0; color: #cbd5e1; font-size: 0.95rem; }
            .dot { color: #4ade80; margin-right: 5px; font-size: 1.2rem; }

            .controls-row { display: flex; justify-content: space-between; gap:10px; margin-bottom: 15px; }
            .btn-mode { padding: 10px; border-radius: 4px; width: 48%; cursor: pointer; border: none; font-weight: bold; transition: 0.2s;}
            .active-auto { background-color: #4ade80; color: #064e3b; }
            .active-manual { background-color: #f87171; color: #450a0a; }
            .inactive { background-color: #334155; color: #94a3b8; border: 1px solid #475569; }
            .manual-actions { display: none; gap: 10px; justify-content: space-between; }
            .btn-action { padding: 8px; border-radius: 4px; border: 1px solid #38bdf8; background: #0f172a; color: #38bdf8; cursor: pointer; width: 48%; font-weight:bold;}
            .btn-action:hover { background: #38bdf8; color: #0f172a; }

            .btn-detect-on  { background-color: #f87171; color: #450a0a; width: 100%; padding: 10px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }
            .btn-detect-off { background-color: #4ade80; color: #064e3b; width: 100%; padding: 10px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }

            ul { margin: 0; padding-left: 20px; color: #cbd5e1; font-size: 0.95rem; }
            li { margin-bottom: 5px; }

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
                top: 0; left: 0;
                width: 100vw; height: 100vh;
                background: rgba(0, 0, 0, 0.6);
                z-index: 1999;
                display: none;
                align-items: center;
                justify-content: center;
            }
            .editor-modal-content {
                width: 80vw; height: 80vh;
                background: #1e1e1e;
                border-radius: 6px;
                box-shadow: 0 0 10px #000;
                display: flex; flex-direction: column;
            }
            @media (max-width: 768px) {
                .editor-modal-content { width: 95vw; height: 90vh; }
            }
            .editor-modal-header {
                height: 40px;
                display: flex; align-items: center; justify-content: space-between;
                padding: 0 10px;
                background: #222;
                color: #fff;
                font-size: 14px;
            }
            .editor-close-btn {
                border: none; background: transparent; color: #fff; cursor: pointer; font-size: 16px;
            }
        </style>
    </head>
    <body>

        <button id="settings-btn" class="settings-button">⚙</button>

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

        <!-- Violation Lightbox -->
        <div id="lightbox" class="lightbox-overlay">
            <div class="lightbox-img-wrap">
                <button class="lightbox-close" id="lightbox-close">✕</button>
                <img id="lightbox-img" src="" alt="Violation">
            </div>
            <div class="lightbox-meta" id="lightbox-meta"></div>
        </div>

        <div class="main-container">
            <div class="video-section">
                <div class="panel-title">Live Camera Feeds</div>
                <div class="video-grid">
                    <div class="camera-card">
                        <div class="camera-title">🚗 Car Camera</div>
                        <div class="video-box car-lane-overlay">
                            <div class="placeholder">Car Detection Stream</div>
                            <img id="streamImgCar" alt="" style="display:none;">
                            <svg id="laneOverlay" class="lane-overlay" viewBox="0 0 100 100" preserveAspectRatio="none">
                                <line id="laneLine1" x1="43" y1="0" x2="33" y2="100"></line>
                                <line id="laneLine2" x1="57" y1="0" x2="66" y2="100"></line>
                            </svg>
                        </div>
                        <details class="lane-tuning-container">
                            <summary class="lane-tuning-header">Lane Boundaries Tuning</summary>
                            <div class="lane-slider-grid">
                                <div class="lane-slider-col">
                                    <div class="lane-slider-title" style="color: #38bdf8;">Left Line</div>
                                    <div class="lane-slider-item left-boundary-slider">
                                        <div class="lane-slider-head"><span>Top</span><span id="val-b1-top">0.430</span></div>
                                        <input id="slider-b1-top" type="range" min="0.05" max="0.95" step="0.001">
                                    </div>
                                    <div class="lane-slider-item left-boundary-slider" style="margin-top: 10px;">
                                        <div class="lane-slider-head"><span>Bottom</span><span id="val-b1-bottom">0.330</span></div>
                                        <input id="slider-b1-bottom" type="range" min="0.05" max="0.95" step="0.001">
                                    </div>
                                </div>
                                <div class="lane-slider-col">
                                    <div class="lane-slider-title" style="color: #f43f5e;">Right Line</div>
                                    <div class="lane-slider-item right-boundary-slider">
                                        <div class="lane-slider-head"><span>Top</span><span id="val-b2-top">0.570</span></div>
                                        <input id="slider-b2-top" type="range" min="0.05" max="0.95" step="0.001">
                                    </div>
                                    <div class="lane-slider-item right-boundary-slider" style="margin-top: 10px;">
                                        <div class="lane-slider-head"><span>Bottom</span><span id="val-b2-bottom">0.660</span></div>
                                        <input id="slider-b2-bottom" type="range" min="0.05" max="0.95" step="0.001">
                                    </div>
                                </div>
                            </div>
                            <div id="lane-boundary-status" class="lane-boundary-status"></div>
                        </details>
                    </div>
                    <div class="camera-card">
                        <div class="camera-title">🚶 Person/Wheelchair Camera</div>
                        <div class="video-box">
                            <div class="placeholder">Person/Wheelchair Detection Stream</div>
                            <img id="streamImgPerson" alt="" style="display:none;">
                        </div>
                    </div>
                </div>

                <!-- ===== VIOLATIONS GALLERY ===== -->
                <div class="violations-section">
                    <div class="violations-header">
                        <div class="panel-title">
                            🚨 Captured Violations
                            <span class="violations-badge" id="violations-count">0</span>
                        </div>
                        <button class="violations-clear-btn" id="violations-clear-btn" onclick="clearViolationsUI()">Clear All</button>
                    </div>
                    <div class="violations-grid" id="violations-grid">
                        <div class="violations-empty">
                            <div class="empty-icon">📷</div>
                            No violations captured yet.
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
            // ===== LANE BOUNDARIES =====
            let laneBoundaries = {
                boundary1_top: 0.43, boundary1_bottom: 0.33,
                boundary2_top: 0.57, boundary2_bottom: 0.66,
                revision: 0, updated_at_ms: 0
            };
            let laneBoundaryPostTimer = null;
            let laneBoundarySyncTimer = null;
            let laneBoundaryDraggingUntil = 0;

            function toFixed3(v) { return Number(v).toFixed(3); }

            function setLaneBoundaryStatus(msg, isError=false) {
                const el = document.getElementById('lane-boundary-status');
                if (!el) return;
                el.textContent = msg || '';
                el.style.color = isError ? '#f87171' : '#94a3b8';
            }

            function applyLaneOverlay(boundaries) {
                const line1 = document.getElementById('laneLine1');
                const line2 = document.getElementById('laneLine2');
                if (!line1 || !line2) return;
                line1.setAttribute('x1', boundaries.boundary1_top * 100);
                line1.setAttribute('y1', 0);
                line1.setAttribute('x2', boundaries.boundary1_bottom * 100);
                line1.setAttribute('y2', 100);
                line2.setAttribute('x1', boundaries.boundary2_top * 100);
                line2.setAttribute('y1', 0);
                line2.setAttribute('x2', boundaries.boundary2_bottom * 100);
                line2.setAttribute('y2', 100);
            }

            function nowMs() { return Date.now(); }

            function isBoundaryStateNewer(incoming, current) {
                const inRev = Number((incoming && incoming.revision) || 0);
                const curRev = Number((current && current.revision) || 0);
                if (inRev > curRev) return true;
                if (inRev < curRev) return false;
                const inTs = Number((incoming && incoming.updated_at_ms) || 0);
                const curTs = Number((current && current.updated_at_ms) || 0);
                return inTs > curTs;
            }

            function syncSliderUI(boundaries) {
                const mappings = [
                    ['boundary1_top', 'slider-b1-top', 'val-b1-top'],
                    ['boundary1_bottom', 'slider-b1-bottom', 'val-b1-bottom'],
                    ['boundary2_top', 'slider-b2-top', 'val-b2-top'],
                    ['boundary2_bottom', 'slider-b2-bottom', 'val-b2-bottom']
                ];
                mappings.forEach(([key, sliderId, valueId]) => {
                    const slider = document.getElementById(sliderId);
                    const valueEl = document.getElementById(valueId);
                    if (slider) slider.value = boundaries[key];
                    if (valueEl) valueEl.textContent = toFixed3(boundaries[key]);
                });
                applyLaneOverlay(boundaries);
            }

            function currentSliderBoundaries() {
                return {
                    boundary1_top: Number(document.getElementById('slider-b1-top').value),
                    boundary1_bottom: Number(document.getElementById('slider-b1-bottom').value),
                    boundary2_top: Number(document.getElementById('slider-b2-top').value),
                    boundary2_bottom: Number(document.getElementById('slider-b2-bottom').value)
                };
            }

            function validateBoundaries(boundaries) {
                if (boundaries.boundary1_top >= boundaries.boundary2_top)
                    return 'Boundary 1 Top 必須小於 Boundary 2 Top';
                if (boundaries.boundary1_bottom >= boundaries.boundary2_bottom)
                    return 'Boundary 1 Bottom 必須小於 Boundary 2 Bottom';
                return null;
            }

            function postLaneBoundaries(boundaries) {
                const validationError = validateBoundaries(boundaries);
                if (validationError) { setLaneBoundaryStatus(validationError, true); return; }
                fetch(`/lane_boundaries?t=${Date.now()}`, {
                    method: 'POST', cache: 'no-store',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(boundaries)
                })
                .then(r => r.json())
                .then(data => {
                    if (!data.success) { setLaneBoundaryStatus(data.error || '更新失敗', true); return; }
                    laneBoundaries = data.lane_boundaries;
                    syncSliderUI(laneBoundaries);
                    setLaneBoundaryStatus('Boundary 已套用（即時）');
                })
                .catch(() => setLaneBoundaryStatus('網路錯誤，更新失敗', true));
            }

            function scheduleLaneBoundaryUpdate() {
                const boundaries = currentSliderBoundaries();
                syncSliderUI(boundaries);
                laneBoundaryDraggingUntil = nowMs() + 800;
                if (laneBoundaryPostTimer) clearTimeout(laneBoundaryPostTimer);
                laneBoundaryPostTimer = setTimeout(() => postLaneBoundaries(boundaries), 120);
            }

            function bindLaneBoundarySliders() {
                ['slider-b1-top', 'slider-b1-bottom', 'slider-b2-top', 'slider-b2-bottom'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.addEventListener('input', scheduleLaneBoundaryUpdate);
                });
            }

            function loadLaneBoundaries() {
                fetch(`/lane_boundaries?t=${Date.now()}`, { cache: 'no-store' })
                    .then(r => r.json())
                    .then(data => {
                        laneBoundaries = data;
                        syncSliderUI(laneBoundaries);
                        setLaneBoundaryStatus(`Boundary 已載入（rev ${data.revision || 0}）`);
                    })
                    .catch(() => {
                        syncSliderUI(laneBoundaries);
                        setLaneBoundaryStatus('Boundary 載入失敗，使用預設值', true);
                    });
            }

            function pollLaneBoundariesForSync() {
                fetch(`/lane_boundaries?t=${Date.now()}`, { cache: 'no-store' })
                    .then(r => r.json())
                    .then(data => {
                        if (!data || typeof data.revision !== 'number') return;
                        const isNewer = isBoundaryStateNewer(data, laneBoundaries);
                        const isDragging = nowMs() < laneBoundaryDraggingUntil;
                        if (isNewer && !isDragging) {
                            laneBoundaries = data;
                            syncSliderUI(laneBoundaries);
                            setLaneBoundaryStatus(`Boundary 已同步（rev ${data.revision}）`);
                        }
                    })
                    .catch(() => {});
            }

            function startLaneBoundarySyncPolling() {
                if (laneBoundarySyncTimer) clearInterval(laneBoundarySyncTimer);
                laneBoundarySyncTimer = setInterval(pollLaneBoundariesForSync, 1000);
            }

            // ===== VIOLATIONS GALLERY =====
            let knownViolationTimestamps = new Set();
            let violationsUIList = [];   // local mirror, newest-first

            function formatViolationTime(ts_ms) {
                const d = new Date(ts_ms);
                const pad = n => String(n).padStart(2, '0');
                return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
                     + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
            }

            function openLightbox(filename, ts_ms, vehicleCount) {
                const lb = document.getElementById('lightbox');
                const img = document.getElementById('lightbox-img');
                const meta = document.getElementById('lightbox-meta');
                img.src = `/violation_image/${filename}`;
                meta.innerHTML = `<strong>${vehicleCount} vehicle${vehicleCount !== 1 ? 's' : ''} detected</strong> &nbsp;·&nbsp; ${formatViolationTime(ts_ms)} &nbsp;·&nbsp; ${filename}`;
                lb.classList.add('open');
            }

            function closeLightbox() {
                document.getElementById('lightbox').classList.remove('open');
                document.getElementById('lightbox-img').src = '';
            }

            function buildViolationCard(v, isNew) {
                const card = document.createElement('div');
                card.className = 'violation-card';
                card.dataset.ts = v.timestamp;
                card.title = `Click to enlarge — ${v.vehicles_detected} vehicle(s) detected`;
                card.onclick = () => openLightbox(v.filename, v.timestamp, v.vehicles_detected);

                if (isNew) {
                    const badge = document.createElement('div');
                    badge.className = 'violation-new-badge';
                    badge.textContent = 'NEW';
                    card.appendChild(badge);
                    // Remove NEW badge after 5 seconds
                    setTimeout(() => badge.remove(), 5000);
                }

                const img = document.createElement('img');
                img.className = 'violation-thumb';
                img.alt = 'Violation';
                img.loading = 'lazy';
                img.src = `/violation_image/${v.filename}`;
                img.onerror = function() {
                    this.style.display = 'none';
                    const ph = document.createElement('div');
                    ph.className = 'violation-thumb-placeholder';
                    ph.textContent = '📷';
                    this.parentNode.insertBefore(ph, this);
                };
                card.appendChild(img);

                const info = document.createElement('div');
                info.className = 'violation-info';
                info.innerHTML = `
                    <div class="violation-time">${formatViolationTime(v.timestamp)}</div>
                    <div class="violation-vehicles">🚗 ${v.vehicles_detected} vehicle${v.vehicles_detected !== 1 ? 's' : ''} detected</div>
                `;
                card.appendChild(info);
                return card;
            }

            function renderViolationsGrid(newRecords) {
                const grid = document.getElementById('violations-grid');
                const countBadge = document.getElementById('violations-count');
                if (!grid) return;

                newRecords.forEach(v => {
                    if (knownViolationTimestamps.has(v.timestamp)) return;
                    knownViolationTimestamps.add(v.timestamp);
                    violationsUIList.unshift(v); // newest first

                    // Remove empty placeholder if present
                    const emptyEl = grid.querySelector('.violations-empty');
                    if (emptyEl) emptyEl.remove();

                    const card = buildViolationCard(v, true);
                    grid.insertBefore(card, grid.firstChild);
                });

                countBadge.textContent = violationsUIList.length;
            }

            function clearViolationsUI() {
                const grid = document.getElementById('violations-grid');
                const countBadge = document.getElementById('violations-count');
                if (!grid) return;
                grid.innerHTML = `<div class="violations-empty"><div class="empty-icon">📷</div>No violations captured yet.</div>`;
                knownViolationTimestamps.clear();
                violationsUIList = [];
                countBadge.textContent = '0';
            }

            function pollViolations() {
                fetch(`/violations?t=${Date.now()}`, { cache: 'no-store' })
                    .then(r => r.json())
                    .then(data => {
                        if (data && Array.isArray(data.violations)) {
                            renderViolationsGrid(data.violations);
                        }
                    })
                    .catch(() => {});
            }

            // ===== SYSTEM CONTROLS =====
            function renderSystemMode(mode) {
                const btnAuto = document.getElementById('btn-auto');
                const btnManual = document.getElementById('btn-manual');
                const manualActions = document.getElementById('manual-actions');
                if (!btnAuto || !btnManual || !manualActions) return;
                if (mode === 'MANUAL') {
                    btnAuto.className = 'btn-mode inactive';
                    btnManual.className = 'btn-mode active-manual';
                    manualActions.style.display = 'flex';
                    return;
                }
                btnAuto.className = 'btn-mode active-auto';
                btnManual.className = 'btn-mode inactive';
                manualActions.style.display = 'none';
            }

            function renderDetectionButton(isOn) {
                const btn = document.getElementById('btn-detect');
                if (!btn) return;
                if (isOn) {
                    btn.textContent = '⏹ Stop Detection';
                    btn.className = 'btn-detect-on';
                    return;
                }
                btn.textContent = '▶ Start Detection';
                btn.className = 'btn-detect-off';
            }

            // ===== LIVE STATS POLL =====
            setInterval(() => {
                fetch(`/stats?t=${Date.now()}`, { cache: 'no-store' })
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('val-persons').innerText = data.persons;
                        document.getElementById('val-cars').innerText = data.cars;
                        document.getElementById('val-wheelchairs').innerText = data.wheelchairs || 0;

                        let uiState = "⏳ Awaiting AI Detection...";
                        if (data.light_state === "PED_WHEELCHAIR") uiState = "♿ Wheelchair Priority (Extended)";
                        else if (data.light_state === "CAR_GREEN") uiState = "🟢 Green - Vehicles (N/S)";
                        else if (data.light_state === "PED_LONG") uiState = "🚶 Pedestrian (Extended)";
                        else if (data.light_state === "PED_SHORT") uiState = "🚶 Pedestrian (Standard)";
                        else if (data.light_state === "MANUAL_OVERRIDE")
                            uiState = "⚠️ Manual Override: " + (data.last_manual_label || "Unknown");

                        document.getElementById('val-state').innerText = uiState;
                        connectStreamIfNeeded('streamImgCar', '/video_feed_car', data.stream_car_online);
                        connectStreamIfNeeded('streamImgPerson', '/video_feed_person', data.stream_person_online);
                        renderSystemMode(data.mode);

                        if (data.lane_boundaries && typeof data.lane_boundaries.revision === 'number') {
                            const isDragging = nowMs() < laneBoundaryDraggingUntil;
                            if (!isDragging && isBoundaryStateNewer(data.lane_boundaries, laneBoundaries)) {
                                laneBoundaries = data.lane_boundaries;
                                syncSliderUI(laneBoundaries);
                                setLaneBoundaryStatus(`Boundary 已同步（rev ${laneBoundaries.revision}）`);
                            }
                        }

                        // Sync violations from stats payload (avoids extra request)
                        if (Array.isArray(data.violations)) {
                            renderViolationsGrid(data.violations);
                        }

                        renderDetectionButton(data.detection);
                    })
                    .catch(err => console.error(err));
            }, 1000);

            // Also poll /violations every 3s as a fallback
            setInterval(pollViolations, 3000);

            function toggleDetection() {
                fetch('/toggle_detection', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => renderDetectionButton(data.detection));
            }

            function setMode(mode) {
                fetch('/set_mode', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({mode: mode})
                })
                .then(r => r.json())
                .then(data => renderSystemMode(data.mode));
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
                    setTimeout(() => { btn.innerText = originalText; btn.disabled = false; }, 1000);
                });
            }

            function connectStreamIfNeeded(imgId, streamUrl, isOnline) {
                const img = document.getElementById(imgId);
                if (!img) return;
                img.dataset.wantOnline = isOnline ? '1' : '0';
                if (isOnline) {
                    if (!img.dataset.connected || img.dataset.connected !== '1') {
                        img.dataset.connected = '1';
                        img.onload = function() { this.style.display = 'block'; };
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
                    if (img.dataset.connected === '1') img.removeAttribute('src');
                    img.style.display = 'none';
                    img.dataset.connected = '0';
                }
            }

            // ===== INIT =====
            document.addEventListener('DOMContentLoaded', function () {
                connectStreamIfNeeded('streamImgCar', '/video_feed_car', false);
                connectStreamIfNeeded('streamImgPerson', '/video_feed_person', false);
                bindLaneBoundarySliders();
                loadLaneBoundaries();
                startLaneBoundarySyncPolling();
                pollViolations();

                // Lightbox close handlers
                document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
                document.getElementById('lightbox').addEventListener('click', function(e) {
                    if (e.target === this) closeLightbox();
                });
                document.addEventListener('keydown', function(e) {
                    if (e.key === 'Escape') closeLightbox();
                });

                // Editor modal
                const settingsBtn = document.getElementById('settings-btn');
                const editorModal = document.getElementById('editor-modal');
                const editorClose = document.getElementById('editor-close');
                const editorFrame = document.getElementById('editor-frame');
                if (settingsBtn && editorModal && editorClose && editorFrame) {
                    settingsBtn.addEventListener('click', function () {
                        if (!editorFrame.src && editorFrame.dataset.src) editorFrame.src = editorFrame.dataset.src;
                        editorModal.style.display = 'flex';
                    });
                    editorClose.addEventListener('click', function () { editorModal.style.display = 'none'; });
                    editorModal.addEventListener('click', function (e) {
                        if (e.target === editorModal) editorModal.style.display = 'none';
                    });
                }
            });
        </script>
    </body>
    </html>
    """
