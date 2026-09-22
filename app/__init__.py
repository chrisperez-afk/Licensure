import os

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

from app.config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.auth import auth_bp
    from app.routes import main_bp
    from app.csv_import import csv_bp
    from app.foamfrat import foamfrat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(csv_bp)
    app.register_blueprint(foamfrat_bp)

    from app.cli import register_cli, seed_admin_if_configured, seed_defaults
    register_cli(app)

    from app.template_helpers import register_template_helpers
    register_template_helpers(app)

    with app.app_context():
        seed_defaults()
        seed_admin_if_configured()

    return app
