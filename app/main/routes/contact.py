from flask import render_template, current_app
from app.main import main_bp

@main_bp.get("/contact")
def contact():
    return render_template(
        "pages/contact.html",
        discord_invite_url=current_app.config.get("DISCORD_INVITE_URL", ""),
        discord_server_name=current_app.config.get("DISCORD_SERVER_NAME", "notre Discord"),
        contact_email=current_app.config.get("CONTACT_EMAIL", ""),
    )