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