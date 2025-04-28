from flask import Flask
from .config import Config
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config.from_object(Config)

    db.init_app(app)

    # register Blueprints
    from .routes.dashboard import dashboard_bp
    from .routes.entries    import entries_bp
    from .routes.agency     import agency_bp
    from .routes.cargo      import cargo_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(entries_bp)
    app.register_blueprint(agency_bp)
    app.register_blueprint(cargo_bp)

    return app