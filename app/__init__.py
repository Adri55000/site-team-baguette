from dotenv import load_dotenv
from flask import Flask, flash, redirect, url_for, request
from flask_babel import Babel
import os
from datetime import datetime
from app.config import TOURNAMENTS
from app.auth.models import User
from flask_login import LoginManager
from .database import close_db, get_db
from app.jinja_filters import display_team_name
from app.errors import register_error_handlers
from pathlib import Path
from app.modules.tournaments import is_casual_tournament, overlay_player_name
from flask_babel import gettext as _

login_manager = LoginManager()

def create_app():
    load_dotenv()

    app = Flask(__name__, instance_relative_config=True)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY manquante. Définis-la via une variable d’environnement (ou .env en local).")

    register_error_handlers(app)
    # Chemin vers la base de données
    
    instance_base = Path(app.instance_path)
    (instance_base / "indices" / "sessions").mkdir(parents=True, exist_ok=True)
    app.config["DATABASE"] = os.path.join(app.instance_path, "database.db")
    
    app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 Mo
    
    app.config['DISCORD_INVITE_URL'] = "https://discord.gg/rHJDPc2FcZ"
    app.config['DISCORD_SERVER_NAME'] = "Team Baguette"
    app.config['CONTACT_EMAIL'] = "contact.teambaguette@gmail.com"
    
    # Gestion de la langue
    app.config['BABEL_DEFAULT_LOCALE'] = "fr"
    app.config['BABEL_SUPPORTED_LOCALES'] = ["fr","en"]
    
    def select_locale():
        lang = request.cookies.get("lang")
        if lang in app.config["BABEL_SUPPORTED_LOCALES"]:
            return lang
        return app.config['BABEL_DEFAULT_LOCALE']

    
    Babel(app, locale_selector=select_locale)
    
    # S'assurer que le dossier instance existe
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    # Fermeture automatique des connexions DB
    app.teardown_appcontext(close_db)

    def format_datetime(value):
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%d/%m/%Y – %H:%M:%S")
        except Exception:
            return value  # fallback si format inattendu

    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["team_name"] = display_team_name
    app.jinja_env.globals["current_tournament_slug"] = "ssr-s4"
    app.jinja_env.globals["is_casual_tournament"] = is_casual_tournament
    app.jinja_env.filters["overlay_player_name"] = overlay_player_name


    app.config["TOURNAMENTS"] = TOURNAMENTS

    from app.context import inject_tournaments, inject_restreams

    app.context_processor(inject_tournaments)
    app.context_processor(inject_restreams)



    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    
    @login_manager.unauthorized_handler
    def unauthorized():
        flash(_("Vous devez être connecté pour accéder à cette page."), "error")
        return redirect(url_for("auth.login"))
        
    @login_manager.user_loader
    def load_user(user_id):
        db = get_db()
        row = db.execute("""
            SELECT
                id,
                username,
                role,
                avatar_filename,
                created_at,
                last_login,
                is_active
            FROM users
            WHERE id = ?
        """, (user_id,)).fetchone()

        return User(row) if row else None

    @app.context_processor
    def inject_role_helpers():
        from app.permissions.roles import has_required_role
        from flask_login import current_user
        def has_role(role):
            if not current_user.is_authenticated:
                return False
            return has_required_role(current_user.role, role)

        return dict(has_role=has_role)
        
    @app.context_processor
    def inject_current_lang():
        lang = request.cookies.get("lang", "fr")
        return {
            "current_lang": lang
        }

    # Import des blueprints
    from .auth.routes import auth_bp
    from app.main import main_bp
    from .restream.routes import restream_bp
    from app.admin import admin_bp

    # Enregistrement des blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(restream_bp)
    app.register_blueprint(admin_bp)


    return app
