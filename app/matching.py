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
