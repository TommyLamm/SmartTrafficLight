from .routes_controls import bp_controls
from .routes_detect import bp_detect
from .routes_digital_twin import bp_digital_twin
from .routes_editor import bp_editor
from .routes_stream import bp_stream
from .routes_ui import bp_ui


def register_blueprints(app):
    app.register_blueprint(bp_detect)
    app.register_blueprint(bp_stream)
    app.register_blueprint(bp_controls)
    app.register_blueprint(bp_digital_twin)
    app.register_blueprint(bp_editor)
    app.register_blueprint(bp_ui)
