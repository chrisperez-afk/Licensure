from datetime import date

from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

# Official, public, one-record-at-a-time verification lookup tools.
# There is no public API for either — these are for a human to double-check
# a single provider's record by hand.
DSHS_VERIFY_URL = (
    "https://www.dshs.texas.gov/dshs-ems-trauma-systems/"
    "ems-personnel-certification-licensure/live-online-certification-licensee"
)
NREMT_VERIFY_URL = "https://www.nremt.org/verify-credentials"

VERIFICATION_SOURCES = {
    "DSHS": {"label": "Texas DSHS", "url": DSHS_VERIFY_URL},
    "NREMT": {"label": "NREMT", "url": NREMT_VERIFY_URL},
    "OTHER": {"label": "Other", "url": None},
}

STATUS_EXPIRED = "expired"
STATUS_CRITICAL = "critical"
STATUS_WARNING = "warning"
STATUS_CURRENT = "current"

STATUS_LABELS = {
    STATUS_EXPIRED: "Expired",
    STATUS_CRITICAL: "Expiring Soon",
    STATUS_WARNING: "Renew Soon",
    STATUS_CURRENT: "Current",
}


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Agency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    providers = db.relationship(
        "Provider", back_populates="agency", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return self.name


class CertificationType(db.Model):
    """A configurable catalog entry, e.g. 'NREMT-Paramedic' or 'TCCC'."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    default_source = db.Column(db.String(10), default="OTHER", nullable=False)

    certifications = db.relationship("Certification", back_populates="cert_type")

    def __repr__(self):
        return self.name


class Provider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    employee_id = db.Column(db.String(40))
    rank_title = db.Column(db.String(80))
    email = db.Column(db.String(255))
    phone = db.Column(db.String(40))
    active = db.Column(db.Boolean, default=True, nullable=False)

    # Free text, not a fixed A/B/C enum — the department's own shift
    # roster export also has values like "ADMIN" and "SMART".
    shift = db.Column(db.String(20))

    # NREMT's own per-person identifier (stable across name changes and
    # credential level upgrades, unlike a certificate number). Backfilled
    # automatically the first time someone is matched during an NREMT
    # roster sync.
    nremt_ems_id = db.Column(db.String(40))

    # FoamFrat's own per-person identifier, for matching once API access
    # exists. Not populated by anything yet.
    foamfrat_user_id = db.Column(db.String(40))

    agency_id = db.Column(db.Integer, db.ForeignKey("agency.id"), nullable=False)
    agency = db.relationship("Agency", back_populates="providers")

    certifications = db.relationship(
        "Certification", back_populates="provider", cascade="all, delete-orphan",
        order_by="Certification.expiration_date",
    )
    assignment_completions = db.relationship(
        "AssignmentCompletion", back_populates="provider", cascade="all, delete-orphan"
    )

    @property
    def full_name(self):
        return f"{self.last_name}, {self.first_name}"

    def worst_status(self):
        """Most urgent status across this provider's certifications."""
        order = [STATUS_EXPIRED, STATUS_CRITICAL, STATUS_WARNING, STATUS_CURRENT]
        statuses = [c.status() for c in self.certifications if c.expiration_date]
        for s in order:
            if s in statuses:
                return s
        return None


class Certification(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    provider_id = db.Column(db.Integer, db.ForeignKey("provider.id"), nullable=False)
    provider = db.relationship("Provider", back_populates="certifications")

    cert_type_id = db.Column(
        db.Integer, db.ForeignKey("certification_type.id"), nullable=False
    )
    cert_type = db.relationship("CertificationType", back_populates="certifications")

    certificate_number = db.Column(db.String(80))
    issue_date = db.Column(db.Date)
    expiration_date = db.Column(db.Date)

    source = db.Column(db.String(10), default="OTHER", nullable=False)
    last_verified_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    # A bookmarked link straight to this person's record on the issuing
    # site (e.g. a Texas DSHS datamart "detailsTXRAS.do?anchor=..." URL),
    # captured after looking them up once. Overrides the generic search
    # link below when present, so "Check on DSHS/NREMT" jumps straight to
    # their record instead of the search form.
    direct_verify_url = db.Column(db.String(500))

    def days_until_expiration(self):
        if not self.expiration_date:
            return None
        return (self.expiration_date - date.today()).days

    def status(self):
        days = self.days_until_expiration()
        if days is None:
            return None
        warning_days = current_app.config.get("WARNING_DAYS", 90)
        critical_days = current_app.config.get("CRITICAL_DAYS", 30)
        if days < 0:
            return STATUS_EXPIRED
        if days <= critical_days:
            return STATUS_CRITICAL
        if days <= warning_days:
            return STATUS_WARNING
        return STATUS_CURRENT

    def verify_url(self):
        return self.direct_verify_url or VERIFICATION_SOURCES.get(self.source, {}).get("url")


COMPLETION_NOT_STARTED = "not_started"
COMPLETION_IN_PROGRESS = "in_progress"
COMPLETION_COMPLETED = "completed"

COMPLETION_LABELS = {
    COMPLETION_NOT_STARTED: "Not Started",
    COMPLETION_IN_PROGRESS: "In Progress",
    COMPLETION_COMPLETED: "Completed",
}


class Assignment(db.Model):
    """A CE assignment pushed out via FoamFrat (or entered by hand until
    API access exists) — e.g. "Airway Management Recert 2026"."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_date = db.Column(db.Date)
    due_date = db.Column(db.Date)

    completions = db.relationship(
        "AssignmentCompletion", back_populates="assignment", cascade="all, delete-orphan"
    )

    def progress(self):
        total = len(self.completions)
        completed = sum(1 for c in self.completions if c.status == COMPLETION_COMPLETED)
        return completed, total


class AssignmentCompletion(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    provider_id = db.Column(db.Integer, db.ForeignKey("provider.id"), nullable=False)
    provider = db.relationship("Provider", back_populates="assignment_completions")

    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False)
    assignment = db.relationship("Assignment", back_populates="completions")

    status = db.Column(db.String(20), default=COMPLETION_NOT_STARTED, nullable=False)
    completed_date = db.Column(db.Date)
    notes = db.Column(db.Text)
