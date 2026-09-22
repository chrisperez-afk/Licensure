"""
Parses the shift roster export from the department's staffing/HR system
(Employee ID / Employee Name / Home Cost Center / Email Address / ... —
"Home Cost Center" is where the shift value lives, e.g. "A", "B", "C",
"ADMIN"). The file itself is an HTML table saved with an .xls extension
rather than a real Excel binary, which is common for this kind of export.
"""

import re

from bs4 import BeautifulSoup

from app import db
from app.matching import find_matching_providers_in
from app.models import Provider
from app.name_format import titlecase_name

EXPECTED_COLUMNS = ["Employee ID", "Employee Name", "Home Cost Center", "Email Address"]


def parse_shift_roster(file_obj):
    """Returns (records, skipped_count). Each record: last_name,
    first_name, employee_id, shift, email."""
    content = file_obj.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    soup = BeautifulSoup(content, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("Couldn't find a table in that file.")

    rows = table.find_all("tr")
    if not rows:
        raise ValueError("That file doesn't have any rows.")

    header_cells = [c.get_text(strip=True) for c in rows[0].find_all("td")]

    def col_index(name):
        try:
            return header_cells.index(name)
        except ValueError:
            return None

    idx_id = col_index("Employee ID")
    idx_name = col_index("Employee Name")
    idx_shift = col_index("Home Cost Center")
    idx_email = col_index("Email Address")

    if idx_name is None or idx_shift is None:
        raise ValueError(
            "Couldn't find the expected columns (Employee Name, Home Cost "
            "Center) in that file."
        )

    def get(cells, idx):
        return cells[idx].strip() if idx is not None and idx < len(cells) else ""

    records = []
    skipped = 0

    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if not cells or all(not c for c in cells):
            continue

        raw_name = get(cells, idx_name)
        if not raw_name or "," not in raw_name:
            skipped += 1
            continue

        last_name, _, first_name = raw_name.partition(",")
        last_name = last_name.strip()
        first_name = first_name.strip()
        if not last_name or not first_name:
            skipped += 1
            continue

        # This HR system's own workaround for two people sharing a name:
        # it appends a digit to the second person's last name in its own
        # records (e.g. "GARZA2, ADRIAN" alongside "GARZA, ADRIAN"). Strip
        # it so both land back on the real last name for matching and
        # storage — sync_shift_roster's employee-ID-aware matching is what
        # then keeps two such people distinct instead of collapsing them.
        last_name = re.sub(r"\d+$", "", last_name).strip() or last_name
        last_name = titlecase_name(last_name)
        first_name = titlecase_name(first_name)

        records.append(
            {
                "raw_name": raw_name,
                "last_name": last_name,
                "first_name": first_name,
                "employee_id": get(cells, idx_id) or None,
                "shift": get(cells, idx_shift) or None,
                "email": get(cells, idx_email) or None,
            }
        )

    return records, skipped


def sync_shift_roster(records, agency):
    """Upsert shift/employee ID/email onto providers for an agency.

    Matched by employee ID first (the HR system's own stable identifier),
    falling back to name (case/suffix-insensitive, so this also lines up
    with providers created by the DSHS/NREMT syncs), and creating a new
    provider only if neither matches — same prefetch-once-and-match-in-
    memory approach as the other syncs, learned the hard way from an
    out-of-memory crash caused by querying per record instead.

    When a name match returns more than one candidate — a genuine name
    collision, like two different people who are both "Adrian Garza" —
    picking the first one blindly would silently reassign whichever
    candidate this loop happens to reach first, on every sync. Instead,
    only accept a name-matched candidate that isn't already claimed by a
    *different* employee ID; if every candidate is already someone else's
    record, fall through to creating a new provider rather than guess.
    """
    stats = {"providers_created": 0, "providers_updated": 0}

    providers = Provider.query.filter(Provider.agency_id == agency.id).all()
    providers_by_employee_id = {p.employee_id: p for p in providers if p.employee_id}

    for rec in records:
        provider = providers_by_employee_id.get(rec["employee_id"]) if rec["employee_id"] else None

        if not provider:
            matches = find_matching_providers_in(rec["first_name"], rec["last_name"], providers)
            provider = next(
                (p for p in matches if not p.employee_id or p.employee_id == rec["employee_id"]),
                None,
            )

        if provider:
            stats["providers_updated"] += 1
        else:
            provider = Provider(
                first_name=rec["first_name"], last_name=rec["last_name"], agency_id=agency.id
            )
            db.session.add(provider)
            db.session.flush()
            providers.append(provider)
            stats["providers_created"] += 1

        provider.shift = rec["shift"]
        if rec["employee_id"]:
            provider.employee_id = rec["employee_id"]
            providers_by_employee_id[rec["employee_id"]] = provider
        if rec["email"]:
            provider.email = rec["email"]

    db.session.commit()
    return stats
