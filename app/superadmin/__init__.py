from flask import Blueprint


superadmin_bp = Blueprint(
    "superadmin",
    __name__,
    url_prefix="/superadmin",
)


from app.superadmin import routes
from app.superadmin import work_requests

from app.superadmin import system
from app.superadmin import system_user_management