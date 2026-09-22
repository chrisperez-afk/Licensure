# EMS Licensure Dashboard

Tracks EMS certification/licensure expiration dates for providers at Bexar
County 2 Fire Department (and, optionally, Bergheim Volunteer Fire
Department) — Texas DSHS EMS certifications, NREMT certifications, and any
other credential you want to watch (CPR/BLS, ACLS, PALS, TCCC, PHTLS, etc).

## Important: how this actually gets DSHS/NREMT data

Neither the **Texas DSHS EMS Certification Verification** tool nor the
**NREMT Verify Credentials** tool offers a public API or bulk-download feed.
Both are one-record-at-a-time web lookups intended for a human to check a
single person, and both are behind bot-protection that makes automated
scraping unreliable and (per their terms) inappropriate to script.

So this app does **not** pull data automatically. Instead:

- You enter each provider's certification number and expiration date once
  (by hand, or via the CSV bulk importer).
- The dashboard tracks expirations and color-codes anything expired or
  coming due (default: red at 0 days, orange at 30 days, yellow at 90 days).
- Each certification row has a **"Check on DSHS/NREMT ↗"** link that opens
  the official verification page in a new tab so you (or whoever's doing
  credentialing that week) can manually confirm the record.
- After confirming, click **"Verified Today"** to log the check and update
  the expiration date if it changed.

This keeps the workflow honest: the dashboard is your single source of
truth for *who's coming due and needs a recheck*, and the official sites
remain the source of truth for the actual certification status.

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

1. **Add providers** one at a time (`Add Provider`) or in bulk (`Import
   CSV` — download the template first, it shows the expected columns).
2. **Add certifications** on each provider's detail page: type, certificate
   number, source (DSHS/NREMT/Other), issue date, expiration date.
3. Watch the **Dashboard** — the summary cards at the top show counts of
   expired / expiring in 30 days / expiring in 90 days / current. Click a
   card to filter the table to just those.
4. When a certification is coming due, click **Check on DSHS/NREMT ↗** on
   that row, confirm the current status/expiration on the official site,
   update the expiration date if needed, and click **Verified Today**.
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
