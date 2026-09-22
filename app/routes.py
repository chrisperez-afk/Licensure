from datetime import date, datetime

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db
from app.models import (
    Agency,
    Certification,
    CertificationType,
    Provider,
    STATUS_CRITICAL,
    STATUS_EXPIRED,
    STATUS_LABELS,
    STATUS_WARNING,
    VERIFICATION_SOURCES,
)

main_bp = Blueprint("main", __name__)


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


@main_bp.route("/")
@login_required
def index():
    return redirect(url_for("main.dashboard"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    agency_id = request.args.get("agency_id", type=int)
    cert_type_id = request.args.get("cert_type_id", type=int)
    status_filter = request.args.get("status")
    search = request.args.get("q", "").strip()
    show_inactive = request.args.get("show_inactive") == "1"

    query = Certification.query.join(Provider).join(CertificationType)

    if agency_id:
        query = query.filter(Provider.agency_id == agency_id)
    if cert_type_id:
        query = query.filter(Certification.cert_type_id == cert_type_id)
    if not show_inactive:
        query = query.filter(Provider.active.is_(True))
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Provider.first_name.ilike(like),
                Provider.last_name.ilike(like),
                Certification.certificate_number.ilike(like),
            )
        )

    certifications = query.filter(Certification.expiration_date.isnot(None)).all()

    if status_filter:
        certifications = [c for c in certifications if c.status() == status_filter]

    certifications.sort(
        key=lambda c: c.expiration_date or date.max
    )

    counts = {STATUS_EXPIRED: 0, STATUS_CRITICAL: 0, STATUS_WARNING: 0, "current": 0}
    all_certs_for_counts = Certification.query.join(Provider).filter(
        Certification.expiration_date.isnot(None)
    )
    if not show_inactive:
        all_certs_for_counts = all_certs_for_counts.filter(Provider.active.is_(True))
    if agency_id:
        all_certs_for_counts = all_certs_for_counts.filter(Provider.agency_id == agency_id)
    for c in all_certs_for_counts.all():
        s = c.status()
        counts[s] = counts.get(s, 0) + 1

    agencies = Agency.query.order_by(Agency.name).all()
    cert_types = CertificationType.query.order_by(CertificationType.name).all()

    return render_template(
        "dashboard.html",
        certifications=certifications,
        counts=counts,
        status_labels=STATUS_LABELS,
        agencies=agencies,
        cert_types=cert_types,
        agency_id=agency_id,
        cert_type_id=cert_type_id,
        status_filter=status_filter,
        search=search,
        show_inactive=show_inactive,
    )


@main_bp.route("/export.csv")
@login_required
def export_csv():
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Agency", "Last Name", "First Name", "Employee ID", "Rank/Title",
            "Certification", "Certificate Number", "Source", "Issue Date",
            "Expiration Date", "Days Until Expiration", "Status", "Last Verified",
        ]
    )
    certs = Certification.query.join(Provider).order_by(
        Provider.last_name, Provider.first_name
    ).all()
    for c in certs:
        writer.writerow(
            [
                c.provider.agency.name,
                c.provider.last_name,
                c.provider.first_name,
                c.provider.employee_id or "",
                c.provider.rank_title or "",
                c.cert_type.name,
                c.certificate_number or "",
                c.source,
                c.issue_date.isoformat() if c.issue_date else "",
                c.expiration_date.isoformat() if c.expiration_date else "",
                c.days_until_expiration() if c.expiration_date else "",
                STATUS_LABELS.get(c.status(), ""),
                c.last_verified_date.isoformat() if c.last_verified_date else "",
            ]
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=licensure-export-{date.today().isoformat()}.csv"
        },
    )


# ---- Providers ----

@main_bp.route("/providers/new", methods=["GET", "POST"])
@login_required
def provider_new():
    agencies = Agency.query.order_by(Agency.name).all()
    if request.method == "POST":
        provider = Provider(
            first_name=request.form["first_name"].strip(),
            last_name=request.form["last_name"].strip(),
            employee_id=request.form.get("employee_id", "").strip() or None,
            rank_title=request.form.get("rank_title", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            agency_id=request.form["agency_id"],
            active=True,
        )
        db.session.add(provider)
        db.session.commit()
        flash(f"Added {provider.full_name}.", "success")
        return redirect(url_for("main.provider_detail", provider_id=provider.id))
    return render_template("provider_form.html", provider=None, agencies=agencies)


@main_bp.route("/providers/<int:provider_id>")
@login_required
def provider_detail(provider_id):
    provider = db.get_or_404(Provider, provider_id)
    cert_types = CertificationType.query.order_by(CertificationType.name).all()
    return render_template(
        "provider_detail.html",
        provider=provider,
        cert_types=cert_types,
        sources=VERIFICATION_SOURCES,
        status_labels=STATUS_LABELS,
    )


@main_bp.route("/providers/<int:provider_id>/edit", methods=["GET", "POST"])
@login_required
def provider_edit(provider_id):
    provider = db.get_or_404(Provider, provider_id)
    agencies = Agency.query.order_by(Agency.name).all()
    if request.method == "POST":
        provider.first_name = request.form["first_name"].strip()
        provider.last_name = request.form["last_name"].strip()
        provider.employee_id = request.form.get("employee_id", "").strip() or None
        provider.rank_title = request.form.get("rank_title", "").strip() or None
        provider.email = request.form.get("email", "").strip() or None
        provider.phone = request.form.get("phone", "").strip() or None
        provider.agency_id = request.form["agency_id"]
        provider.active = request.form.get("active") == "on"
        db.session.commit()
        flash(f"Updated {provider.full_name}.", "success")
        return redirect(url_for("main.provider_detail", provider_id=provider.id))
    return render_template("provider_form.html", provider=provider, agencies=agencies)


@main_bp.route("/providers/<int:provider_id>/delete", methods=["POST"])
@login_required
def provider_delete(provider_id):
    provider = db.get_or_404(Provider, provider_id)
    name = provider.full_name
    db.session.delete(provider)
    db.session.commit()
    flash(f"Removed {name}.", "success")
    return redirect(url_for("main.dashboard"))


# ---- Certifications ----

@main_bp.route("/providers/<int:provider_id>/certifications/new", methods=["POST"])
@login_required
def certification_new(provider_id):
    provider = db.get_or_404(Provider, provider_id)
    cert = Certification(
        provider_id=provider.id,
        cert_type_id=request.form["cert_type_id"],
        certificate_number=request.form.get("certificate_number", "").strip() or None,
        issue_date=_parse_date(request.form.get("issue_date")),
        expiration_date=_parse_date(request.form.get("expiration_date")),
        source=request.form.get("source", "OTHER"),
        notes=request.form.get("notes", "").strip() or None,
    )
    db.session.add(cert)
    db.session.commit()
    flash("Certification added.", "success")
    return redirect(url_for("main.provider_detail", provider_id=provider.id))


@main_bp.route("/certifications/<int:cert_id>/edit", methods=["POST"])
@login_required
def certification_edit(cert_id):
    cert = db.get_or_404(Certification, cert_id)
    cert.cert_type_id = request.form["cert_type_id"]
    cert.certificate_number = request.form.get("certificate_number", "").strip() or None
    cert.issue_date = _parse_date(request.form.get("issue_date"))
    cert.expiration_date = _parse_date(request.form.get("expiration_date"))
    cert.source = request.form.get("source", "OTHER")
    cert.notes = request.form.get("notes", "").strip() or None
    db.session.commit()
    flash("Certification updated.", "success")
    return redirect(url_for("main.provider_detail", provider_id=cert.provider_id))


@main_bp.route("/certifications/<int:cert_id>/verify", methods=["POST"])
@login_required
def certification_verify(cert_id):
    """Mark that a human checked the official DSHS/NREMT site today."""
    cert = db.get_or_404(Certification, cert_id)
    cert.last_verified_date = date.today()
    new_expiration = request.form.get("expiration_date")
    if new_expiration:
        cert.expiration_date = _parse_date(new_expiration)
    db.session.commit()
    flash("Marked as verified today.", "success")
    return redirect(url_for("main.provider_detail", provider_id=cert.provider_id))


@main_bp.route("/certifications/<int:cert_id>/delete", methods=["POST"])
@login_required
def certification_delete(cert_id):
    cert = db.get_or_404(Certification, cert_id)
    provider_id = cert.provider_id
    db.session.delete(cert)
    db.session.commit()
    flash("Certification removed.", "success")
    return redirect(url_for("main.provider_detail", provider_id=provider_id))


# ---- Agencies & certification types (lightweight settings) ----

@main_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "agency":
            name = request.form.get("name", "").strip()
            if name and not Agency.query.filter_by(name=name).first():
                db.session.add(Agency(name=name))
                db.session.commit()
                flash(f"Added agency '{name}'.", "success")
        elif form_type == "cert_type":
            name = request.form.get("name", "").strip()
            source = request.form.get("default_source", "OTHER")
            if name and not CertificationType.query.filter_by(name=name).first():
                db.session.add(CertificationType(name=name, default_source=source))
                db.session.commit()
                flash(f"Added certification type '{name}'.", "success")
        return redirect(url_for("main.settings"))

    agencies = Agency.query.order_by(Agency.name).all()
    cert_types = CertificationType.query.order_by(CertificationType.name).all()
    return render_template(
        "settings.html",
        agencies=agencies,
        cert_types=cert_types,
        sources=VERIFICATION_SOURCES,
    )
