from flask import 
from . import homepage, user_profile, public_profile, tournaments_display, contact

main_bp = Blueprint("main", __name__)

from . import routes