import ast
import importlib

from flask import Blueprint, jsonify, request

import logic

from ..config import LOGIC_PATH


bp_editor = Blueprint("editor", __name__)


@bp_editor.route('/get_code')
def get_code():
    try:
        with open(LOGIC_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"File Error: {str(e)}", 500


@bp_editor.route('/save_code', methods=['POST'])
def save_code():
    new_code = request.form.get("code")
    try:
        ast.parse(new_code)
    except SyntaxError as e:
        return jsonify({"success": False, "error": f"Line {e.lineno}: {e.msg}\nSnippet: {e.text}"}), 400

    try:
        with open(LOGIC_PATH, 'w', encoding='utf-8') as f:
            f.write(new_code)

        importlib.reload(logic)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
