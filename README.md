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
current.

For anything DSHS doesn't cover — NREMT certifications, CPR/BLS, ACLS,
TCCC, and so on — use manual entry or **Import CSV** the same way, and use
the **"Check on DSHS/NREMT ↗"** link on any certification row (opens the
official verification page) plus **"Verified Today"** to log a manual
spot-check the same way the roster sync does automatically.

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

1. **Sync DSHS Roster** first — this gets most of your roster and their
   Texas certifications in one paste (see above).
2. **Add providers** one at a time (`Add Provider`) or in bulk (`Import
   CSV` — download the template first, it shows the expected columns) for
   anyone DSHS doesn't cover, or for NREMT/other credentials.
3. Watch the **Dashboard** — the summary cards at the top show counts of
   expired / expiring in 30 days / expiring in 90 days / current. Click a
   card to filter the table to just those.
4. For anything not covered by the DSHS sync, click **Check on DSHS/NREMT
   ↗** on that row, confirm the current status/expiration on the official
   site, update the expiration date if needed, and click **Verified
   Today**.
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
