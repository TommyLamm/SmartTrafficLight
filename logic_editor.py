"""
logic_editor.py — Standalone Web-based Algorithm Editor
========================================================
Run alongside app.py (no extra packages needed):
    python3 logic_editor.py

Then open in your browser:
    http://<your-server-ip>:5001

Features:
- Edit logic.py directly in browser
- Syntax check before saving
- Hot-reloads the running Flask app on port 5000 after save
- Uses only Python built-in libraries (http.server, ast, urllib)
"""

import ast
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT       = 5001
HOST       = "0.0.0.0"
LOGIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logic.py")
FLASK_RELOAD = "http://127.0.0.1:5000/save_code"


def read_logic():
    try:
        with open(LOGIC_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"# ERROR reading file: {e}"


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Algorithm Editor - logic.py</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0b1121; color: #94a3b8; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; height: 100vh; display: flex; flex-direction: column; }
  header { background: #171e2e; border-bottom: 1px solid #1e293b; padding: 10px 20px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
  header h1 { color: #38bdf8; font-size: 1rem; flex: 1; }
  button { padding: 8px 18px; border-radius: 5px; border: none; font-weight: bold; cursor: pointer; font-size: 0.9rem; }
  #btn-save   { background: #38bdf8; color: #0f172a; }
  #btn-save:disabled { background: #1e4976; color: #94a3b8; cursor: not-allowed; }
  #btn-reload { background: #334155; color: #e2e8f0; border: 1px solid #475569; }
  #status { font-size: 0.85rem; padding: 6px 14px; border-radius: 4px; background: #1e293b; }
  #editor-wrap { display: flex; flex: 1; overflow: hidden; }
  #line-nums { background: #1e293b; color: #4b5563; font-family: "Courier New", monospace; font-size: 13px; padding: 10px 8px; text-align: right; user-select: none; overflow: hidden; white-space: pre; line-height: 1.6; min-width: 46px; }
  #editor { flex: 1; background: #0f172a; color: #4ade80; font-family: "Courier New", monospace; font-size: 13px; border: none; outline: none; resize: none; padding: 10px 14px; line-height: 1.6; tab-size: 4; }
  #error-bar { display: none; background: #7f1d1d; color: #fca5a5; padding: 10px 20px; font-family: monospace; white-space: pre-wrap; font-size: 0.85rem; flex-shrink: 0; border-top: 1px solid #991b1b; }
  footer { background: #171e2e; border-top: 1px solid #1e293b; padding: 5px 20px; font-size: 0.78rem; color: #475569; flex-shrink: 0; }
</style>
</head>
<body>
<header>
  <h1>Algorithm Editor - logic.py</h1>
  <span id="status">Ready</span>
  <button id="btn-reload" onclick="reloadFromDisk()">Reload from Disk</button>
  <button id="btn-save"   onclick="saveCode()">Save &amp; Apply</button>
</header>

<div id="editor-wrap">
  <div id="line-nums">1</div>
  <textarea id="editor" spellcheck="false">PLACEHOLDER</textarea>
</div>

<div id="error-bar"></div>
<footer>Ctrl+S = Save &amp; Apply | Connected to Flask on port 5000</footer>

<script>
const editor   = document.getElementById('editor');
const lineNums = document.getElementById('line-nums');
const status   = document.getElementById('status');
const errorBar = document.getElementById('error-bar');
const btnSave  = document.getElementById('btn-save');

function updateLineNums() {
  const lines = editor.value.split('\n').length;
  lineNums.textContent = Array.from({length: lines}, (_, i) => i + 1).join('\n');
}
function syncScroll() { lineNums.scrollTop = editor.scrollTop; }
editor.addEventListener('input',  updateLineNums);
editor.addEventListener('scroll', syncScroll);

editor.addEventListener('keydown', e => {
  if (e.key === 'Tab') {
    e.preventDefault();
    const s = editor.selectionStart;
    editor.value = editor.value.substring(0, s) + '    ' + editor.value.substring(editor.selectionEnd);
    editor.selectionStart = editor.selectionEnd = s + 4;
    updateLineNums();
  }
  if (e.ctrlKey && e.key === 's') { e.preventDefault(); saveCode(); }
});

function setStatus(msg, color) {
  status.textContent = msg;
  status.style.color = color || '#94a3b8';
}

function reloadFromDisk() {
  fetch('/get_code').then(r => r.text()).then(code => {
    editor.value = code; updateLineNums();
    setStatus('Reloaded from disk', '#4ade80');
    setTimeout(() => setStatus('Ready', ''), 3000);
  });
}

function saveCode() {
  errorBar.style.display = 'none';
  btnSave.disabled = true;
  btnSave.textContent = 'Saving...';
  setStatus('Saving...', '#38bdf8');

  fetch('/save_code', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'code=' + encodeURIComponent(editor.value)
  })
    .then(r => r.json())
    .then(data => {
      btnSave.disabled = false;
      btnSave.textContent = 'Save & Apply';
      if (data.success) {
        setStatus('Saved & hot-reloaded!', '#4ade80');
        setTimeout(() => setStatus('Ready', ''), 4000);
      } else {
        errorBar.textContent = 'ERROR:\n' + data.error;
        errorBar.style.display = 'block';
        setStatus('Error - see below', '#f87171');
      }
    })
    .catch(err => {
      btnSave.disabled = false;
      btnSave.textContent = 'Save & Apply';
      errorBar.textContent = 'Network error: ' + err.message;
      errorBar.style.display = 'block';
      setStatus('Network error', '#f87171');
    });
}

updateLineNums();
</script>
</body>
</html>
"""


class EditorHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  [{self.address_string()}] {fmt % args}")

    def send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, status=200):
        import json
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            code = read_logic()
            safe = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            page = HTML_TEMPLATE.replace("PLACEHOLDER", safe)
            self.send_html(page)

        elif self.path == "/get_code":
            code = read_logic()
            body = code.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_html("<h1>404</h1>", 404)

    def do_POST(self):
        if self.path == "/save_code":
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length).decode("utf-8")
            # JS sends application/x-www-form-urlencoded — no cgi needed
            params = urllib.parse.parse_qs(raw, keep_blank_values=True)
            code   = params.get("code", [""])[0]

            # 1. Syntax check
            try:
                ast.parse(code)
            except SyntaxError as e:
                self.send_json({"success": False,
                                "error": f"Line {e.lineno}: {e.msg}\nSnippet: {e.text}"})
                return

            # 2. Write to disk
            try:
                with open(LOGIC_PATH, "w", encoding="utf-8") as f:
                    f.write(code)
            except Exception as e:
                self.send_json({"success": False, "error": f"File write failed: {e}"})
                return

            # 3. Tell Flask to hot-reload (best-effort)
            try:
                post_data = urllib.parse.urlencode({"code": code}).encode("utf-8")
                req = urllib.request.Request(FLASK_RELOAD, data=post_data, method="POST")
                urllib.request.urlopen(req, timeout=3)
            except urllib.error.URLError:
                # File saved — Flask just isn't reachable; not a failure
                pass

            self.send_json({"success": True})

        else:
            self.send_html("<h1>404</h1>", 404)


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), EditorHandler)
    print(f"Editor running  ->  http://127.0.0.1:{PORT}")
    print(f"Editing file    ->  {LOGIC_PATH}")
    print(f"Flask target    ->  {FLASK_RELOAD}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEditor stopped.")
        sys.exit(0)
