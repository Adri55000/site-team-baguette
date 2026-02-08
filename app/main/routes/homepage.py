from flask import render_template, abort, make_response, redirect, url_for, request
from .. import main_bp

@main_bp.route("/")
def home():
    return render_template("main/index.html")

@main_bp.get("/lang/<lang>")
def set_lang(lang):
    if lang not in ("fr", "en"):
        abort(404)

    resp = make_response(
        redirect(request.referrer or url_for("main.index"))
    )

    # cookie long terme, comme le thème
    resp.set_cookie(
        "lang",
        lang,
        max_age=60 * 60 * 24 * 365,  # 1 an
        samesite="Lax"
    )

    return resp