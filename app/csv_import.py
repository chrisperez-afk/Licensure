import csv
import io
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.dshs_roster import parse_dshs_roster, sync_dshs_roster
from app.matching import find_matching_providers_in
from app.models import Agency, Certification, CertificationType, Provider
from app.name_format import titlecase_name
from app.nremt_roster import parse_nremt_roster, sync_nremt_roster
from app.shift_roster import parse_shift_roster, sync_shift_roster

csv_bp = Blueprint("csv_import", __name__, url_prefix="/import")

REQUIRED_COLUMNS = ["first_name", "last_name", "agency"]
OPTIONAL_COLUMNS = [
    "employee_id", "shift", "rank_title", "email", "phone",
    "certification", "certificate_number", "source",
    "issue_date", "expiration_date", "direct_verify_url",
]

TEMPLATE_HEADER = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


@csv_bp.route("/template.csv")
@login_required
def template():
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(TEMPLATE_HEADER)
    writer.writerow(
        [
            "Jane", "Doe", "Bexar County 2 Fire Department", "1234", "A",
            "Firefighter/Paramedic", "jane.doe@example.com", "210-555-0100",
            "NREMT - Paramedic", "E123456", "NREMT", "2023-01-15", "2027-01-15", "",
        ]
    )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=roster-import-template.csv"},
    )


@csv_bp.route("", methods=["GET", "POST"])
@login_required
def import_csv():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or file.filename == "":
            flash("Choose a CSV file to upload.", "danger")
            return redirect(url_for("csv_import.import_csv"))

        try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
        except UnicodeDecodeError:
            flash("Could not read that file. Save it as UTF-8 CSV and try again.", "danger")
            return redirect(url_for("csv_import.import_csv"))

        reader = csv.DictReader(stream)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            flash(
                f"CSV is missing required column(s): {', '.join(missing)}. "
                f"Download the template below for the expected format.",
                "danger",
            )
            return redirect(url_for("csv_import.import_csv"))

        providers_created = 0
        providers_updated = 0
        certs_created = 0
        row_errors = []

        # Cached per agency (a CSV usually covers one agency, but can
        # cover several) so matching a name against the existing roster
        # is one query per agency for the whole import, not one query per
        # row — the latter is what ran a roster sync out of memory on a
        # small hosted instance (see dshs_roster.py/nremt_roster.py).
        providers_by_agency = {}

        for i, row in enumerate(reader, start=2):  # row 1 is the header
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            agency_name = (row.get("agency") or "").strip()

            if not first_name or not last_name or not agency_name:
                row_errors.append(f"Row {i}: missing first name, last name, or agency.")
                continue
            first_name = titlecase_name(first_name)
            last_name = titlecase_name(last_name)

            agency = Agency.query.filter_by(name=agency_name).first()
            if not agency:
                agency = Agency(name=agency_name)
                db.session.add(agency)
                db.session.flush()

            if agency.id not in providers_by_agency:
                providers_by_agency[agency.id] = Provider.query.filter(
                    Provider.agency_id == agency.id
                ).all()
            candidates = providers_by_agency[agency.id]

            matches = find_matching_providers_in(first_name, last_name, candidates)
            if matches:
                provider = matches[0]
                providers_updated += 1
            else:
                provider = Provider(first_name=first_name, last_name=last_name, agency_id=agency.id)
                db.session.add(provider)
                db.session.flush()
                candidates.append(provider)
                providers_created += 1

            employee_id = (row.get("employee_id") or "").strip()
            if employee_id:
                provider.employee_id = employee_id
            shift = (row.get("shift") or "").strip()
            if shift:
                provider.shift = shift
            rank_title = (row.get("rank_title") or "").strip()
            if rank_title:
                provider.rank_title = rank_title
            email = (row.get("email") or "").strip()
            if email:
                provider.email = email
            phone = (row.get("phone") or "").strip()
            if phone:
                provider.phone = phone

            db.session.flush()

            cert_name = (row.get("certification") or "").strip()
            if cert_name:
                cert_type = CertificationType.query.filter_by(name=cert_name).first()
                if not cert_type:
                    cert_type = CertificationType(
                        name=cert_name,
                        default_source=(row.get("source") or "OTHER").strip().upper() or "OTHER",
                    )
                    db.session.add(cert_type)
                    db.session.flush()

                cert = Certification.query.filter_by(
                    provider_id=provider.id, cert_type_id=cert_type.id
                ).first()
                if not cert:
                    cert = Certification(provider_id=provider.id, cert_type_id=cert_type.id)
                    db.session.add(cert)
                    certs_created += 1

                cert_number = (row.get("certificate_number") or "").strip()
                if cert_number:
                    cert.certificate_number = cert_number
                source = (row.get("source") or "").strip().upper()
                if source in ("DSHS", "NREMT", "OTHER"):
                    cert.source = source
                issue_date = _parse_date(row.get("issue_date"))
                if issue_date:
                    cert.issue_date = issue_date
                expiration_date = _parse_date(row.get("expiration_date"))
                if expiration_date:
                    cert.expiration_date = expiration_date
                direct_verify_url = (row.get("direct_verify_url") or "").strip()
                if direct_verify_url:
                    cert.direct_verify_url = direct_verify_url

        db.session.commit()

        summary = (
            f"Import complete: {providers_created} provider(s) added, "
            f"{providers_updated} matched/updated, {certs_created} certification(s) added."
        )
        flash(summary, "success")
        for err in row_errors[:20]:
            flash(err, "warning")

        return redirect(url_for("main.dashboard"))

    return render_template("import.html")


@csv_bp.route("/dshs-roster", methods=["GET", "POST"])
@login_required
def dshs_roster():
    agencies = Agency.query.order_by(Agency.name).all()

    if request.method == "POST":
        agency_id = request.form.get("agency_id", type=int)
        pasted_text = request.form.get("roster_text", "")

        agency = db.session.get(Agency, agency_id) if agency_id else None
        if not agency:
            flash("Choose which agency this roster belongs to.", "danger")
            return redirect(url_for("csv_import.dshs_roster"))

        if not pasted_text.strip():
            flash("Paste the roster text from the DSHS page first.", "danger")
            return redirect(url_for("csv_import.dshs_roster"))

        records, skipped = parse_dshs_roster(pasted_text)

        if not records:
            flash(
                "Couldn't find any personnel records in that text. Make sure you "
                "copied the section starting at \"Related Party Name\" (or the "
                "whole page), including the Status and Expiration Date lines.",
                "danger",
            )
            return redirect(url_for("csv_import.dshs_roster"))

        stats = sync_dshs_roster(records, agency)

        summary = (
            f"Synced {len(records)} record(s) from DSHS for {agency.name}: "
            f"{stats['providers_created']} new provider(s), "
            f"{stats['certs_created']} new certification(s), "
            f"{stats['certs_updated']} existing certification(s) refreshed "
            f"and marked verified today."
        )
        flash(summary, "success")
        if skipped:
            flash(
                f"{skipped} line(s) in the pasted text looked like a credential row "
                f"but didn't fully match the expected pattern, and were skipped. "
                f"Double check those people got picked up.",
                "warning",
            )

        return redirect(url_for("main.dashboard"))

    return render_template("dshs_roster_import.html", agencies=agencies)


@csv_bp.route("/nremt-roster", methods=["GET", "POST"])
@login_required
def nremt_roster():
    agencies = Agency.query.order_by(Agency.name).all()

    if request.method == "POST":
        agency_id = request.form.get("agency_id", type=int)
        file = request.files.get("roster_file")

        agency = db.session.get(Agency, agency_id) if agency_id else None
        if not agency:
            flash("Choose which agency this roster belongs to.", "danger")
            return redirect(url_for("csv_import.nremt_roster"))

        if not file or file.filename == "":
            flash("Choose the roster file exported from your NREMT account.", "danger")
            return redirect(url_for("csv_import.nremt_roster"))

        try:
            records, skipped = parse_nremt_roster(file.stream)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("csv_import.nremt_roster"))

        if not records:
            flash(
                "Couldn't find any personnel rows in that file. Make sure it's "
                "the roster export with Name/EMS ID/Registry #/Status/Level/"
                "Recert Cycle columns.",
                "danger",
            )
            return redirect(url_for("csv_import.nremt_roster"))

        stats = sync_nremt_roster(records, agency)

        summary = (
            f"Synced {len(records)} record(s) from NREMT for {agency.name}: "
            f"{stats['providers_created']} new provider(s), "
            f"{stats['certs_created']} new certification(s), "
            f"{stats['certs_updated']} existing certification(s) refreshed "
            f"and marked verified today."
        )
        flash(summary, "success")
        if skipped:
            flash(
                f"{skipped} row(s) in the file were missing a name or "
                f"registry number and were skipped.",
                "warning",
            )

        return redirect(url_for("main.dashboard"))

    return render_template("nremt_roster_import.html", agencies=agencies)


@csv_bp.route("/shift-roster", methods=["GET", "POST"])
@login_required
def shift_roster():
    agencies = Agency.query.order_by(Agency.name).all()

    if request.method == "POST":
        agency_id = request.form.get("agency_id", type=int)
        file = request.files.get("roster_file")

        agency = db.session.get(Agency, agency_id) if agency_id else None
        if not agency:
            flash("Choose which agency this roster belongs to.", "danger")
            return redirect(url_for("csv_import.shift_roster"))

        if not file or file.filename == "":
            flash("Choose the shift roster file to upload.", "danger")
            return redirect(url_for("csv_import.shift_roster"))

        try:
            records, skipped = parse_shift_roster(file.stream)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("csv_import.shift_roster"))

        if not records:
            flash(
                "Couldn't find any personnel rows in that file. Make sure it's "
                "the roster export with Employee Name/Home Cost Center columns.",
                "danger",
            )
            return redirect(url_for("csv_import.shift_roster"))

        stats = sync_shift_roster(records, agency)

        summary = (
            f"Synced shifts for {len(records)} record(s) for {agency.name}: "
            f"{stats['providers_created']} new provider(s), "
            f"{stats['providers_updated']} existing provider(s) updated."
        )
        flash(summary, "success")
        if skipped:
            flash(f"{skipped} row(s) in the file had no usable name and were skipped.", "warning")

        return redirect(url_for("main.dashboard"))

    return render_template("shift_roster_import.html", agencies=agencies)
