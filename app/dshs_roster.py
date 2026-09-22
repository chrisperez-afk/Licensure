"""
Parses the plain text you get when you copy the "Related Party Name" roster
section off a Texas DSHS provider page (e.g. the page for license number
1001000 / vo.ras.dshs.state.tx.us/datamart/detailsTXRAS.do?anchor=...) and
paste it into the roster-sync form.

The page renders each person as a small multi-line block inside a table
cell, so a plain-text copy loses the table structure but keeps a very
regular line pattern:

    LASTNAME, FIRST MIDDLE
    <credential description> #<credential number>
    Status:    <status text>
    Expiration Date:    <MM/DD/YYYY or blank>
    <0-4 address lines>

Records are anchored on the "<description> #<number>" line (the one
reliably-unique marker), with the name taken from the line before it and
status/expiration from the two lines after it. Non-person rows (the
department's own listing, roles with no credential number such as
"EMS Administrator #") are dropped by requiring both a comma in the name
(i.e. "Last, First" format) and a non-empty credential number.
"""

from datetime import date, datetime

from app import db
from app.matching import find_matching_providers_in
from app.models import Certification, CertificationType, Provider


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_dshs_roster(text):
    """Returns (records, skipped_count).

    Each record is a dict: raw_name, last_name, first_name,
    cert_description, cert_number, status, expiration_date (date or None),
    section (str or None).
    """
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l != ""]
    n = len(lines)

    section_at = [None] * n
    current_section = None
    for idx in range(n):
        if lines[idx].startswith("Licensee's Role:"):
            current_section = lines[idx - 1] if idx > 0 else None
        section_at[idx] = current_section

    license_idx = [
        k for k in range(n)
        if "#" in lines[k]
        and not lines[k].startswith("Licensee's Role:")
        and not lines[k].startswith("Related Party")
    ]

    records = []
    skipped = 0

    for k in license_idx:
        if k - 1 < 0:
            skipped += 1
            continue
        if k + 1 >= n or not lines[k + 1].startswith("Status:"):
            skipped += 1
            continue

        raw_name = lines[k - 1]
        if "," not in raw_name:
            continue  # not a "Last, First" person row (e.g. the org's own listing)

        desc, _, num = lines[k].rpartition("#")
        cert_description = desc.strip()
        cert_number = num.strip()
        if not cert_number:
            continue  # roles listed with no actual credential number

        status = lines[k + 1][len("Status:"):].strip()

        expiration_raw = ""
        if k + 2 < n and lines[k + 2].startswith("Expiration Date:"):
            expiration_raw = lines[k + 2][len("Expiration Date:"):].strip()

        last_name, _, first_name = raw_name.partition(",")
        last_name = last_name.strip()
        first_name = first_name.strip()
        if not last_name or not first_name:
            skipped += 1
            continue

        records.append(
            {
                "raw_name": raw_name,
                "last_name": last_name,
                "first_name": first_name,
                "cert_description": cert_description,
                "cert_number": cert_number,
                "status": status,
                "expiration_date": _parse_date(expiration_raw),
                "section": section_at[k],
            }
        )

    return records, skipped


def sync_dshs_roster(records, agency):
    """Upsert parsed roster records into providers/certifications for an
    agency.

    Certificate numbers are DSHS's own unique identifiers, so a record is
    matched to an existing certification by number first — this is what
    makes a re-paste safe to repeat (it updates, never duplicates) and what
    keeps two different people who happen to share a name (it happens: two
    "Adrian Garza"s can both work EMS in a metro area) from getting merged
    into one provider and silently overwriting each other's cert data. Only
    when no certification with that number exists yet do we fall back to
    matching an existing provider by name — and even then, only onto a
    same-named provider who doesn't already hold a certification of this
    same type, so a genuine name collision creates a second provider
    instead of clobbering the first one's record.
    """
    today = date.today()
    stats = {
        "providers_created": 0,
        "certs_created": 0,
        "certs_updated": 0,
    }

    cert_type_cache = {}

    def get_cert_type(description):
        if description not in cert_type_cache:
            ct = CertificationType.query.filter_by(name=description).first()
            if not ct:
                ct = CertificationType(name=description, default_source="DSHS")
                db.session.add(ct)
                db.session.flush()
            cert_type_cache[description] = ct
        return cert_type_cache[description]

    # Fetch once and work in memory from here — matching every record
    # against a fresh database query in a loop of this size is what
    # actually ran the process out of memory on a small hosted instance.
    providers = Provider.query.filter(Provider.agency_id == agency.id).all()
    certs_by_number = {
        c.certificate_number: c
        for c in Certification.query.join(Provider).filter(Provider.agency_id == agency.id).all()
        if c.certificate_number
    }

    for rec in records:
        cert_type = get_cert_type(rec["cert_description"])

        existing_cert = certs_by_number.get(rec["cert_number"])

        if existing_cert:
            existing_cert.cert_type_id = cert_type.id
            existing_cert.expiration_date = rec["expiration_date"]
            existing_cert.source = "DSHS"
            existing_cert.last_verified_date = today
            stats["certs_updated"] += 1
            continue

        candidates = find_matching_providers_in(rec["first_name"], rec["last_name"], providers)

        provider = next(
            (
                c
                for c in candidates
                if not any(cert.cert_type_id == cert_type.id for cert in c.certifications)
            ),
            None,
        )

        if not provider:
            provider = Provider(
                first_name=rec["first_name"], last_name=rec["last_name"], agency_id=agency.id
            )
            db.session.add(provider)
            db.session.flush()
            providers.append(provider)
            stats["providers_created"] += 1

        new_cert = Certification(
            provider_id=provider.id,
            cert_type_id=cert_type.id,
            certificate_number=rec["cert_number"],
            expiration_date=rec["expiration_date"],
            source="DSHS",
            last_verified_date=today,
        )
        db.session.add(new_cert)
        certs_by_number[rec["cert_number"]] = new_cert
        stats["certs_created"] += 1

    db.session.commit()
    return stats
