from .. import admin_bp
from flask import render_template
from app.auth.utils import login_required
from app.permissions.decorators import role_required


@admin_bp.route("/")
@login_required
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html")