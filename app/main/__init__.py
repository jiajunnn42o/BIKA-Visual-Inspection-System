from flask import Blueprint


# =========================================================
# MAIN BLUEPRINT
# =========================================================

main_bp = Blueprint(
    "main",
    __name__,
)


# =========================================================
# REGISTER ROUTES
#
# These imports must stay AFTER main_bp is created.
# Otherwise circular imports may occur.
# =========================================================

from app.main import routes
from app.main import about_system
from app.main import backup_destination_picker
from app.main import inspection_routes
from app.main import model_management
from app.main import reports_routes
from app.main import media_routes
from app.main import live_stream_routes