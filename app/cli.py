import os

import click

from app import db
from app.models import Agency, CertificationType, User

DEFAULT_CERT_TYPES = [
    ("NREMT - EMT", "NREMT"),
    ("NREMT - AEMT", "NREMT"),
    ("NREMT - Paramedic", "NREMT"),
    ("Texas DSHS - EMT", "DSHS"),
    ("Texas DSHS - AEMT", "DSHS"),
    ("Texas DSHS - Licensed Paramedic", "DSHS"),
    ("CPR/BLS", "OTHER"),
    ("ACLS", "OTHER"),
    ("PALS", "OTHER"),
    ("TCCC", "OTHER"),
    ("PHTLS", "OTHER"),
]

DEFAULT_AGENCIES = [
    "Bexar County 2 Fire Department",
    "Bergheim Volunteer Fire Department",
]


def seed_defaults():
    """Idempotent: create tables and seed default agencies/certification
    types. Safe to call on every app boot, not just once."""
    db.create_all()

    for name in DEFAULT_AGENCIES:
        if not Agency.query.filter_by(name=name).first():
            db.session.add(Agency(name=name))

    for name, source in DEFAULT_CERT_TYPES:
        if not CertificationType.query.filter_by(name=name).first():
            db.session.add(CertificationType(name=name, default_source=source))

    db.session.commit()


def seed_admin_if_configured():
    """Idempotent: create the initial admin user from ADMIN_* environment
    variables, if ADMIN_PASSWORD is set and that username doesn't already
    exist. Returns True if a user was created. Safe to call on every app
    boot — this is what lets a hosted deploy get a working login just from
    environment variables, with no shell access needed."""
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return False

    username = os.environ.get("ADMIN_USERNAME", "admin")
    if User.query.filter_by(username=username).first():
        return False

    email = os.environ.get("ADMIN_EMAIL", "")
    user = User(username=username, email=email, is_admin=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return True


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create tables and seed default agencies/certification types."""
        seed_defaults()
        click.echo("Database initialized with default agencies and certification types.")

    @app.cli.command("seed-admin")
    def seed_admin():
        """Create the initial admin user from ADMIN_* environment variables."""
        if not os.environ.get("ADMIN_PASSWORD"):
            click.echo("Set ADMIN_PASSWORD (env or .env) before running seed-admin.")
            return
        username = os.environ.get("ADMIN_USERNAME", "admin")
        if User.query.filter_by(username=username).first():
            click.echo(f"User '{username}' already exists; skipping.")
            return
        seed_admin_if_configured()
        click.echo(f"Created admin user '{username}'.")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.password_option()
    def create_user(username, password):
        """Create an additional login (e.g. for another admin/officer)."""
        if User.query.filter_by(username=username).first():
            click.echo(f"User '{username}' already exists.")
            return
        user = User(username=username, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created user '{username}'.")
