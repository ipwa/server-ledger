# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this is

Server Ledger: a small self-hosted Flask app for tracking client billing (who's paying, how much, whether they're paid up or overdue) on self-managed infrastructure. See `README.md` for the user-facing feature list and setup instructions.

## Stack

- **Backend:** Flask (`app.py`), no ORM — raw `sqlite3` via `db.py`.
- **DB:** SQLite, file at `data/server_ledger.db`, schema in `schema.sql`. Created automatically by `db.init_db()` on app startup; a small ad-hoc migration (`db._migrate`) adds columns that were introduced after the initial schema, so schema changes should go in `schema.sql` **and** get a corresponding `_migrate` step if existing databases need to pick them up without a manual reset.
- **Frontend:** server-rendered Jinja templates (`templates/`), one small vanilla-JS file for client-side search/filter (`static/app.js`), hand-written CSS (`static/style.css`). No build step, no JS framework, no bundler.
- **Prod server:** gunicorn (see `requirements.txt`).

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                                    # dev server, http://127.0.0.1:3006/
gunicorn -w 2 -b 127.0.0.1:3006 app:app           # prod-style run
```

There is no test suite, linter, or build step configured. There's also no package manifest beyond `requirements.txt` — don't introduce `npm`/`poetry`/etc. tooling unless the user asks for it.

## Architecture notes

- **Status is derived, not stored.** `db.compute_status()` computes `overdue` / `expiring` / `active` / `internal` from `paid_through_date` vs. today on every read. Never add a `status` column — this is intentional so the dashboard can't show stale status after a payment is edited or deleted.
- **`paid_through_date` is a cache, recomputed from `payments`.** `db.recompute_paid_through()` sets it to `MAX(extends_through_date)` across a client's remaining payments, and is called after every payment insert/edit/delete in `app.py`. If you add a new way to mutate payments, call it there too — don't hand-set `paid_through_date` elsewhere.
- **Personal/internal clients** (`is_personal = 1`) always have `monthly_amount = NULL` and `paid_through_date = NULL`, and are excluded from revenue/KPI calculations in `compute_kpis()`. Enforce this invariant in any new write path, not just the existing ones.
- **Multi-currency totals are never summed across currencies.** `_sum_by_currency()` / `fmt_money_by_currency()` keep a dict keyed by currency code and render each separately, joined with `+`. Don't introduce a single combined total unless you also add currency conversion.
- **Routes serve both HTML forms and JSON.** Most `/admin/...` mutation routes accept either a form POST (redirects back to `/admin`) or a JSON body (returns the updated resource) — see `_wants_json()` / `_client_payload()` in `app.py`. Keep new mutation routes consistent with this dual-mode pattern rather than picking one.
- **No authentication in the app itself.** This is deliberate — auth is expected to be handled by whatever reverse proxy fronts the app in production (Basic Auth, SSO, VPN, etc.). Don't add session/login logic here unless the user explicitly asks for it; if they do, treat it as a real feature request (password hashing, CSRF protection, etc.), not a quick add.

## What's intentionally not in this repo

Deployment files that hardcode a specific server's domain, IP, and file paths (nginx config, systemd unit, provisioning scripts) are excluded via `.gitignore` — this repo is meant to be reusable, so deployment specifics belong in each deployer's own fork/notes rather than in version control here.
