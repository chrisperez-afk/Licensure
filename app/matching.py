import re

from app import db
from app.models import Provider

# Common name suffixes that one source (DSHS) tends to drop and another
# (NREMT) tends to keep attached to the last name, e.g. "Anderson" vs
# "Anderson Jr" for the same person. Stripped for matching purposes only —
# the original text is always what gets stored.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _normalize_last_name(last_name):
    parts = (last_name or "").strip().split()
    if len(parts) > 1 and parts[-1].strip(".").lower() in _SUFFIXES:
        parts = parts[:-1]
    return re.sub(r"[.,]", "", " ".join(parts)).strip().lower()


def _normalize_first_name(first_name):
    return re.sub(r"[.,]", "", (first_name or "").strip()).lower()


def find_matching_providers(first_name, last_name, agency):
    """All providers in an agency whose name matches case- and
    suffix-insensitively, e.g. an all-caps DSHS import ("Anderson,
    Robert B"), an NREMT import that keeps a suffix ("Anderson Jr,
    Robert B"), and a mixed-case manual entry for the same person."""
    target_last = _normalize_last_name(last_name)
    target_first = _normalize_first_name(first_name)

    return [
        candidate
        for candidate in Provider.query.filter(Provider.agency_id == agency.id).all()
        if _normalize_last_name(candidate.last_name) == target_last
        and _normalize_first_name(candidate.first_name) == target_first
    ]


def find_matching_provider(first_name, last_name, agency):
    matches = find_matching_providers(first_name, last_name, agency)
    return matches[0] if matches else None


def find_or_create_provider(first_name, last_name, agency):
    existing = find_matching_provider(first_name, last_name, agency)
    if existing:
        return existing, False

    provider = Provider(first_name=first_name, last_name=last_name, agency_id=agency.id)
    db.session.add(provider)
    db.session.flush()
    return provider, True


_BACKFILL_FIELDS = ["employee_id", "rank_title", "email", "phone", "nremt_ems_id"]


def merge_providers(source, target):
    """Fold `source` into `target`: move every certification over (skipping
    any that would exactly duplicate one `target` already has by
    certificate number), backfill any contact fields `target` is missing
    from `source`, then delete `source`.

    For the case automated matching can't safely resolve on its own — two
    records for what a human knows is the same person, whose names didn't
    line up closely enough (or at all) for the automatic matching in this
    module to have merged them on its own during a sync.
    """
    stats = {"certs_moved": 0, "certs_skipped_duplicate": 0, "fields_backfilled": 0}

    target_numbers = {c.certificate_number for c in target.certifications if c.certificate_number}

    for cert in list(source.certifications):
        if cert.certificate_number and cert.certificate_number in target_numbers:
            db.session.delete(cert)
            stats["certs_skipped_duplicate"] += 1
            continue
        cert.provider_id = target.id
        stats["certs_moved"] += 1

    for field in _BACKFILL_FIELDS:
        if not getattr(target, field) and getattr(source, field):
            setattr(target, field, getattr(source, field))
            stats["fields_backfilled"] += 1

    db.session.delete(source)
    db.session.commit()
    return stats
