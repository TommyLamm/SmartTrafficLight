import os
import subprocess
import sys

from smart_traffic import create_app


app = create_app()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


if __name__ == '__main__':
    editor_path = os.path.join(BASE_DIR, 'logic_editor.py')
    if os.path.exists(editor_path):
        subprocess.Popen([sys.executable, editor_path])
        print("📝 Algorithm Editor  - Open http://127.0.0.1:5001")
    else:
        print("⚠️  logic_editor.py not found — editor will not start.")

    from waitress import serve
    print("🚀 App Running       - Open http://127.0.0.1:5000")
    serve(app, host='127.0.0.1', port=5000, threads=8)
