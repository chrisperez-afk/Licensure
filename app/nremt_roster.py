"""
Parses the roster spreadsheet exported from your NREMT organization
account (Name / EMS ID / Registry # / Status / Level / Recert Cycle /
Agency Name / Email columns) and syncs it into providers/certifications.

Unlike the DSHS page, this file already comes from an authenticated,
agency-scoped NREMT export, so there's no public-page workaround involved
here — it's a straight file upload.
"""

from datetime import date, datetime

from app import db
from app.matching import find_matching_providers_in
from app.models import Certification, CertificationType, Provider
from app.xlsx_utils import load_workbook_safe

EXPECTED_COLUMNS = [
    "Name", "EMS ID", "Registry #", "Status", "Level", "Recert Cycle",
    "Agency Name", "Email",
]


def _parse_cycle_dates(cycle_text):
    """'MM/DD/YY - MM/DD/YY' -> (issue_date, expiration_date), either may
    be None if the text doesn't parse cleanly."""
    cycle_text = (cycle_text or "").strip()
    if " - " not in cycle_text:
        return None, None
    start_text, _, end_text = cycle_text.partition(" - ")

    def parse_one(text):
        for fmt in ("%m/%d/%y", "%m/%d/%Y"):
            try:
                return datetime.strptime(text.strip(), fmt).date()
            except ValueError:
                continue
        return None

    return parse_one(start_text), parse_one(end_text)


def parse_nremt_roster(file_obj):
    """Returns (records, skipped_count). Each record: last_name, first_name,
    ems_id, registry_number, status, level, issue_date, expiration_date,
    agency_name, email."""
    wb = load_workbook_safe(file_obj)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))

    header_idx = None
    for i, row in enumerate(rows):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if "Name" in cells and "EMS ID" in cells:
            header_idx = i
            header = cells
            break

    if header_idx is None:
        raise ValueError(
            "Couldn't find the expected header row (Name, EMS ID, Registry #, "
            "Status, Level, Recert Cycle, Agency Name, Email) in that file."
        )

    col = {name: header.index(name) for name in EXPECTED_COLUMNS if name in header}
    required = ["Name", "Registry #", "Recert Cycle"]
    missing = [c for c in required if c not in col]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}.")

    records = []
    skipped = 0

    for row in rows[header_idx + 1:]:
        if row is None or all(v is None for v in row):
            continue

        def get(name):
            idx = col.get(name)
            return row[idx] if idx is not None and idx < len(row) else None

        raw_name = (get("Name") or "").strip() if get("Name") else ""
        registry_number = (get("Registry #") or "").strip() if get("Registry #") else ""

        if not raw_name or "," not in raw_name or not registry_number:
            skipped += 1
            continue

        last_name, _, first_name = raw_name.partition(",")
        last_name = last_name.strip()
        first_name = first_name.strip()
        if not last_name or not first_name:
            skipped += 1
            continue

        issue_date, expiration_date = _parse_cycle_dates(get("Recert Cycle"))

        ems_id = (get("EMS ID") or "").strip() if get("EMS ID") else ""
        level = (get("Level") or "").strip() if get("Level") else ""
        status = (get("Status") or "").strip() if get("Status") else ""
        agency_name = (get("Agency Name") or "").strip() if get("Agency Name") else ""
        email = (get("Email") or "").strip() if get("Email") else ""

        records.append(
            {
                "raw_name": raw_name,
                "last_name": last_name,
                "first_name": first_name,
                "ems_id": ems_id or None,
                "registry_number": registry_number,
                "status": status,
                "level": level,
                "issue_date": issue_date,
                "expiration_date": expiration_date,
                "agency_name": agency_name,
                "email": email or None,
            }
        )

    return records, skipped


def sync_nremt_roster(records, agency):
    """Upsert parsed NREMT roster records into providers/certifications.

    Matching, in order:
    1. An existing certification with this Registry # (NREMT's own
       identifier for a specific credential) — update it in place. This is
       what makes re-uploading the same or a refreshed export safe.
    2. An existing provider with this NREMT EMS ID (NREMT's stable
       per-person identifier, unaffected by name changes or a credential
       level upgrade that issues a new Registry #) — attach a new
       certification there.
    3. An existing provider matched by name (case/suffix-insensitive, so
       this also links up with providers created by the DSHS roster sync)
       — attach there and backfill their EMS ID for next time.
    4. Otherwise, create a new provider.
    """
    today = date.today()
    stats = {"providers_created": 0, "certs_created": 0, "certs_updated": 0}

    cert_type_cache = {}

    def get_cert_type(level):
        name = f"NREMT - {level}" if level else "NREMT - Unspecified"
        if name not in cert_type_cache:
            ct = CertificationType.query.filter_by(name=name).first()
            if not ct:
                ct = CertificationType(name=name, default_source="NREMT")
                db.session.add(ct)
                db.session.flush()
            cert_type_cache[name] = ct
        return cert_type_cache[name]

    # Fetch once and work in memory from here — three separate database
    # queries per record (by cert number, by EMS ID, by name) in a loop of
    # any real size is slow, and on a memory-constrained host risks
    # running the process out of memory outright rather than just being
    # slow.
    providers = Provider.query.filter(Provider.agency_id == agency.id).all()
    certs_by_number = {
        c.certificate_number: c
        for c in Certification.query.join(Provider).filter(Provider.agency_id == agency.id).all()
        if c.certificate_number
    }
    providers_by_ems_id = {p.nremt_ems_id: p for p in providers if p.nremt_ems_id}

    for rec in records:
        cert_type = get_cert_type(rec["level"])
        notes = f"NREMT status: {rec['status']}" if rec["status"] else None

        existing_cert = certs_by_number.get(rec["registry_number"])

        if existing_cert:
            existing_cert.cert_type_id = cert_type.id
            existing_cert.issue_date = rec["issue_date"]
            existing_cert.expiration_date = rec["expiration_date"]
            existing_cert.source = "NREMT"
            existing_cert.last_verified_date = today
            if notes and (not existing_cert.notes or existing_cert.notes.startswith("NREMT status:")):
                existing_cert.notes = notes
            provider = existing_cert.provider
            if rec["ems_id"] and not provider.nremt_ems_id:
                provider.nremt_ems_id = rec["ems_id"]
                providers_by_ems_id[rec["ems_id"]] = provider
            stats["certs_updated"] += 1
            continue

        provider = providers_by_ems_id.get(rec["ems_id"]) if rec["ems_id"] else None

        if not provider:
            name_matches = find_matching_providers_in(rec["first_name"], rec["last_name"], providers)
            provider = next(
                (
                    p
                    for p in name_matches
                    if not any(c.cert_type_id == cert_type.id for c in p.certifications)
                ),
                None,
            )
            if provider and rec["ems_id"] and not provider.nremt_ems_id:
                provider.nremt_ems_id = rec["ems_id"]
                providers_by_ems_id[rec["ems_id"]] = provider

        if not provider:
            provider = Provider(
                first_name=rec["first_name"],
                last_name=rec["last_name"],
                agency_id=agency.id,
                nremt_ems_id=rec["ems_id"],
                email=rec["email"],
            )
            db.session.add(provider)
            db.session.flush()
            providers.append(provider)
            if rec["ems_id"]:
                providers_by_ems_id[rec["ems_id"]] = provider
            stats["providers_created"] += 1

        new_cert = Certification(
            provider_id=provider.id,
            cert_type_id=cert_type.id,
            certificate_number=rec["registry_number"],
            issue_date=rec["issue_date"],
            expiration_date=rec["expiration_date"],
            source="NREMT",
            last_verified_date=today,
            notes=notes,
        )
        db.session.add(new_cert)
        certs_by_number[rec["registry_number"]] = new_cert
        stats["certs_created"] += 1

    db.session.commit()
    return stats
