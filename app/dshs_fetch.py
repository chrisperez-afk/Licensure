"""
Fetches an agency's DSHS provider page directly over HTTP instead of a
human copying and pasting it into the Sync DSHS Roster form — same page,
same "Related Party Name" roster, just pulled by the app instead of by
hand. No login is involved (the page is public), so this is a plain GET.

The page's markup isn't something we control, so the text this produces
is only an approximation of what a browser-copy gives you: BeautifulSoup
walks the DOM and joins each piece of visible text with a newline, which
lines up with parse_dshs_roster's expectations for table-based markup but
can drift if DSHS changes their page layout. If the nightly/on-demand
fetch stops finding records that a manual paste still finds, that's the
first thing to check.
"""

import requests
from bs4 import BeautifulSoup

from app.dshs_roster import parse_dshs_roster, sync_dshs_roster

REQUEST_TIMEOUT = 30

# Some sites reject the default python-requests UA outright; a normal
# browser UA avoids that without doing anything sneaky (this is a public,
# unauthenticated page, no session/cookie tricks involved).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch_dshs_roster_text(url):
    """Fetch a DSHS provider page and return its visible text, in the same
    line-oriented shape parse_dshs_roster expects from a copy-paste."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Couldn't fetch the DSHS page: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.get_text("\n", strip=True)


def fetch_and_sync_dshs_roster(agency):
    """Fetch + parse + sync an agency's DSHS roster in one shot. Returns
    (stats, skipped) exactly like the paste-based flow does. Raises
    ValueError if the agency has no DSHS URL configured, the fetch fails,
    or the page didn't yield any recognizable records."""
    if not agency.dshs_roster_url:
        raise ValueError(f"'{agency.name}' has no DSHS roster URL configured in Settings.")

    text = fetch_dshs_roster_text(agency.dshs_roster_url)
    records, skipped = parse_dshs_roster(text)

    if not records:
        raise ValueError(
            f"Fetched '{agency.name}'s DSHS page but didn't find any personnel "
            f"records in it. The page layout may have changed, or the URL may "
            f"no longer point at the right page."
        )

    stats = sync_dshs_roster(records, agency)
    return stats, skipped
