from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()


@login_manager.user_loader
def load_user(user_id):
    from app.models import User

    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None