# EMS Licensure Dashboard

Tracks EMS certification/licensure expiration dates for providers at Bexar
County 2 Fire Department (and, optionally, Bergheim Volunteer Fire
Department) — Texas DSHS EMS certifications, NREMT certifications, and any
other credential you want to watch (CPR/BLS, ACLS, PALS, TCCC, PHTLS, etc).

## Important: how this actually gets DSHS/NREMT data

Neither DSHS nor NREMT has a public API. But Texas DSHS's provider page
(the one you get to by looking up your EMS Provider License number, e.g.
`vo.ras.dshs.state.tx.us/datamart/detailsTXRAS.do?anchor=...`) lists every
certified person currently affiliated with your license under
**"Related Party Name"** — that's your whole roster on one page, no login
required, no API needed.

**Sync DSHS Roster** (in the nav bar) is built around exactly that page:

1. Pull up your provider page on DSHS, select the roster section (or the
   whole page — extra text is ignored), and copy it.
2. Paste it into the **Sync DSHS Roster** form and submit.
3. Every person on that page gets added or updated: name, certification
   type, certificate number, and expiration date, all matched by DSHS's own
   certificate number so re-pasting is always safe (it updates existing
   records, it never duplicates them) — and every certification found this
   way is automatically marked **verified today**, since the data just came
   straight from DSHS.

Re-run this any time you want a refresh — weekly, monthly, whatever fits
your credentialing cycle. It's the primary way to keep the dashboard
current for Texas certifications.

NREMT doesn't have a page like that, but it does let you export a roster
of everyone certified under your agency from your NREMT organization
account (Name / EMS ID / Registry # / Status / Level / Recert Cycle
columns). **Sync NREMT Roster** takes that exported file directly:

1. Export your roster from NREMT as a spreadsheet.
2. Upload it under **Sync NREMT Roster**.
3. Everyone gets added or updated — certification level, registry number,
   recert cycle dates — matched by NREMT's own registry number (safe to
   re-upload, same as the DSHS sync) and cross-matched by name against
   anyone already added via the DSHS sync, so one person doesn't end up as
   two separate entries just because they showed up in both sources.

If NREMT marks someone **Inactive** (they can be inactive with NREMT even
if their recert cycle hasn't technically lapsed yet — worth knowing if
you're checking who's actually deployable), that shows up as a red
"Inactive" badge next to their status on the dashboard, and in the Notes
column on their certification, even though the color-coded expiration
status is still date-driven.

For anything neither source covers — CPR/BLS, ACLS, TCCC, and so on — use
manual entry or **Import CSV**, and use the **"Check on DSHS/NREMT ↗"**
link on any certification row (opens the official verification page) plus
**"Verified Today"** to log a manual spot-check the same way the roster
syncs do automatically.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set SECRET_KEY and ADMIN_PASSWORD at minimum

export FLASK_APP=run.py
flask init-db        # creates tables + default agencies/certification types
flask seed-admin      # creates your login from ADMIN_USERNAME/ADMIN_PASSWORD in .env

python3 run.py         # runs on http://0.0.0.0:5000
```

Then log in at `http://<this-machine's-IP>:5000` from any browser on the
same network (e.g. a station computer).

To add another login (e.g. for another officer doing credentialing):

```bash
flask create-user jsmith
```

## Day-to-day use

1. **Sync DSHS Roster** and **Sync NREMT Roster** first — together these
   cover most of your roster and their Texas/national certifications in
   one paste and one upload (see above).
2. **Add providers** one at a time (`Add Provider`) or in bulk (`Import
   CSV` — download the template first, it shows the expected columns) for
   anyone neither sync covers, or for other credentials (CPR/BLS, ACLS,
   TCCC, PHTLS, etc).
3. Watch the **Dashboard** — the summary cards at the top show counts of
   expired / expiring in 30 days / expiring in 90 days / current. Click a
   card to filter the table to just those. A red "Inactive" badge flags
   anyone NREMT lists as inactive.
4. For anything not covered by the roster syncs, click **Check on
   DSHS/NREMT ↗** on that row, confirm the current status/expiration on
   the official site, update the expiration date if needed, and click
   **Verified Today**.
5. **Export CSV** any time for a report to send up the chain or to your
   Medical Director.

## Configuration

Set in `.env` (see `.env.example`):

- `SECRET_KEY` — random string for session signing. Required in production.
- `DATABASE_URL` — defaults to a local SQLite file at `instance/licensure.db`.
- `WARNING_DAYS` / `CRITICAL_DAYS` — thresholds (in days) for the
  yellow/orange color coding. Defaults: 90 and 30.
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` — used once by
  `flask seed-admin` to create the first login.

## Notes on running this for real

- This is a small Flask + SQLite app meant to run on one machine on your
  local network (a station PC, a small server, etc). For anything beyond a
  handful of concurrent users, put it behind a real WSGI server (gunicorn)
  and a reverse proxy (nginx) instead of Flask's dev server.
- The SQLite database (`instance/licensure.db`) contains provider names,
  contact info, and certification numbers — back it up regularly and treat
  it like the PII it is. It's excluded from git via `.gitignore`.
- There is currently no automated email/text alerting; the dashboard is
  pull-based (someone checks it). If you want push alerts (e.g. a weekly
  email digest of what's expiring), that can be added as a scheduled script
  using the same database — ask and it can be built next.
