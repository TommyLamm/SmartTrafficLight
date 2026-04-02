import os
import subprocess
import sys

from smart_traffic import create_app


app = create_app()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_HOST = os.environ.get("SMARTTRAFFIC_APP_HOST", "127.0.0.1")
EDITOR_HOST = os.environ.get("SMARTTRAFFIC_EDITOR_HOST", "127.0.0.1")


def _env_int(name, default):
    value = os.environ.get(name, "")
    if value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


APP_PORT = _env_int("SMARTTRAFFIC_APP_PORT", 5000)
EDITOR_PORT = _env_int("SMARTTRAFFIC_EDITOR_PORT", 5001)
START_EDITOR = os.environ.get("SMARTTRAFFIC_START_EDITOR", "1") != "0"


if __name__ == '__main__':
    editor_path = os.path.join(BASE_DIR, 'logic_editor.py')
    if START_EDITOR and os.path.exists(editor_path):
        subprocess.Popen([sys.executable, editor_path], env=os.environ.copy())
        print(f"📝 Algorithm Editor  - Open http://{EDITOR_HOST}:{EDITOR_PORT}")
    else:
        print("⚠️  logic_editor.py not found — editor will not start.")

    from waitress import serve
    print(f"🚀 App Running       - Open http://{APP_HOST}:{APP_PORT}")
    serve(app, host=APP_HOST, port=APP_PORT, threads=8)
