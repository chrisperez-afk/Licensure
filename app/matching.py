import re

from app import db

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


def _first_names_match(a, b):
    """Exact match, or one source's first name is a truncated version of
    the other's — e.g. an HR export with "MORGAN" for someone DSHS/NREMT
    list under "MORGAN BRADFORD". Matches on the first word only, so this
    doesn't require the middle name/initial to line up, just the actual
    first name."""
    a = _normalize_first_name(a)
    b = _normalize_first_name(b)
    if a == b:
        return True
    a_first = a.split()[0] if a else ""
    b_first = b.split()[0] if b else ""
    return bool(a_first) and a_first == b_first


def find_matching_providers_in(first_name, last_name, candidates):
    """Case- and suffix-insensitive match against an already-fetched list
    of providers — no database query of its own. Use this (fetching the
    candidate list once, outside any loop) for anything matching many
    names in a batch: a per-record query in a loop of any real size turns
    into that many separate round-trips and re-hydrated result sets,
    which is slow in general and, on a memory-constrained host, can run
    the process out of memory outright rather than just being slow."""
    target_last = _normalize_last_name(last_name)

    return [
        candidate
        for candidate in candidates
        if _normalize_last_name(candidate.last_name) == target_last
        and _first_names_match(candidate.first_name, first_name)
    ]


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
