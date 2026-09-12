from flask import Flask

from config import Config
from app.extensions import db, migrate, login_manager, csrf


def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    #login_manager.login_view = "auth.login"

    from app.main import main_bp
    app.register_blueprint(main_bp)

    return app