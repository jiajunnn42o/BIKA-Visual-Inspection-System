from flask import Flask

from config import Config

from app.extensions import (
    csrf,
    db,
    login_manager,
    mail,
    migrate,
)


def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    db.init_app(app)
    from app import workflow_models  # noqa: F401
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = (
        "Please sign in to access this page."
    )
    login_manager.login_message_category = "warning"

    from app import models

    from app.main import main_bp
    app.register_blueprint(main_bp)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.superadmin import superadmin_bp
    from app.notifications import notifications_bp
    app.register_blueprint(superadmin_bp)

    from app.account import account_bp
    app.register_blueprint(account_bp)

    app.register_blueprint(
        notifications_bp
    )

    from app.cli import create_superadmin
    app.cli.add_command(create_superadmin)

    return app