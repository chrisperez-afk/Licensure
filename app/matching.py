from app import db
from app.models import Provider


def find_or_create_provider(first_name, last_name, agency):
    """Case-insensitive match on (first_name, last_name) within an agency,
    so an all-caps DSHS import and a mixed-case manual entry for the same
    person land on one record instead of two."""
    existing = Provider.query.filter(
        Provider.agency_id == agency.id,
        db.func.lower(Provider.first_name) == first_name.lower(),
        db.func.lower(Provider.last_name) == last_name.lower(),
    ).first()
    if existing:
        return existing, False

    provider = Provider(first_name=first_name, last_name=last_name, agency_id=agency.id)
    db.session.add(provider)
    db.session.flush()
    return provider, True
