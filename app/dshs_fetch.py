"""
Fetches an agency's DSHS provider page directly over HTTP instead of a
human copying and pasting it into the Sync DSHS Roster form — same page,
same "Related Party Name" roster, just pulled by the app instead of by
hand. No login is involved (the page is public), so this is a plain GET.

The page's markup isn't something we control, and it turns out a naive
"flatten all text with newlines" doesn't reproduce what a browser copy
gives you: on the real page, a label like "Status:" and its value
("Current/Active") sit in separate <td> cells of the same table row, and
a browser copy joins same-row cells onto one line while a flat text-walk
puts them on separate lines. parse_dshs_roster needs "Status:    <value>"
on one line, so the extraction below reconstructs lines row-by-row instead:
for each <tr>, it joins the text of that row's own <td> cells (skipping any
cell that itself wraps a nested <table>, since that nested table's rows get
their own lines when the walk reaches them). That's what makes multi-cell
rows like "Status:" / "Current/Active" and single merged cells like
"Licensed Paramedic #728763" (colspan) come out the same way a person
copying the page would see them. If the nightly/on-demand fetch stops
finding records that a manual paste still finds, DSHS likely changed this
row structure and this needs re-deriving against the new markup.
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


def _reconstruct_copied_text(soup):
    """Rebuild the page's text the way a browser "select all, copy" of a
    table-based page like this one actually renders it: one line per table
    row, with that row's own cells joined onto that line (not its nested
    tables' cells, which get their own lines when the walk reaches them)."""
    lines = []
    for tr in soup.find_all("tr"):
        cell_texts = []
        for td in tr.find_all("td", recursive=False):
            if td.find("table"):
                continue  # this cell's content is a nested table; its rows get their own lines
            # A single cell's own text can still contain an internal newline
            # (e.g. "Licensed Paramedic\n#728763"), which would otherwise
            # split into two lines below and break the record it belongs to.
            text = " ".join(td.get_text(" ", strip=True).split())
            if text:
                cell_texts.append(text)
        if cell_texts:
            lines.append(" ".join(cell_texts))
    return "\n".join(lines)


def fetch_dshs_roster_text(url):
    """Fetch a DSHS provider page and return its visible text, in the same
    line-oriented shape parse_dshs_roster expects from a copy-paste."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Couldn't fetch the DSHS page: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    return _reconstruct_copied_text(soup)


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
