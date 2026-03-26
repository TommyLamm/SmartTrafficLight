from flask import Blueprint, render_template_string

from .ui_html import INDEX_HTML


bp_ui = Blueprint("ui", __name__)


@bp_ui.route('/')
def index():
    return render_template_string(INDEX_HTML)
