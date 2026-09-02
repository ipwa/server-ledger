# Server Ledger

A tiny self-hosted dashboard for tracking client billing on servers you manage yourself: who's paying, how much, in what currency, and whether they're paid up, expiring soon, or overdue.

Built for the case where you host a handful of client sites/apps on your own infrastructure and just need a lightweight ledger — no invoicing, no payment processing, no SaaS subscription, just a record of what was paid and when coverage runs out.

![status](https://img.shields.io/badge/stack-Flask%20%2B%20SQLite-blue)

## Features

- **Dashboard** — KPI tiles (monthly revenue by currency, active/expiring/overdue counts), a searchable/filterable client roster, and a visual "days left" meter per client.
- **Admin view** — add/edit clients, record payments, and archive (soft-delete) clients no longer in use.
- **Payment history** — each payment records what date range it covers, so a client's `paid_through_date` is always recomputed from the ledger of payments, not hand-edited.
- **Multi-currency** — clients can be billed in different currencies; totals are grouped and shown per-currency rather than incorrectly summed together.
- **Internal/personal clients** — mark a client as personal/non-billed (e.g. your own projects) to exclude it from revenue and status tracking while still listing it.
- **Status computed live** — `overdue` / `expiring` (≤7 days) / `active` / `internal` is derived from `paid_through_date` on every request, never stored, so it can't drift out of sync.
- **Zero JS framework** — server-rendered Jinja templates plus ~30 lines of vanilla JS for client-side search/filter. SQLite for storage. No build step.

## Quickstart

Requires Python 3.10+.

```bash
git clone <this-repo-url> server-ledger
cd server-ledger
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app starts on `http://127.0.0.1:3006/`. A SQLite database is created automatically at `data/server_ledger.db` on first run (schema in `schema.sql`).

Open the dashboard at `/` and manage clients/payments at `/admin`.

## Running in production

`app.py`'s built-in server is for local development only. For production, run it behind gunicorn (already a dependency) and a reverse proxy:

```bash
gunicorn -w 2 -b 127.0.0.1:3006 app:app
```

Then front it with nginx (or your proxy of choice) and terminate TLS there. **The app itself has no authentication** — anyone who can reach the port can view and edit your billing data. If you expose it beyond localhost, put it behind HTTP Basic Auth, a VPN, an SSO proxy, or similar at the reverse-proxy layer, and don't skip TLS.

Consider running it under a process supervisor (systemd, supervisord, etc.) so it restarts on failure and starts on boot.

## Data model

Two tables (see `schema.sql`):

- **`clients`** — name, domain, monthly amount + currency, personal/internal flag, computed-and-cached `paid_through_date`, notes, archived flag.
- **`payments`** — belongs to a client; amount, the date it was paid, and the coverage window (`extends_from_date` → `extends_through_date`) it pays for.

`db.recompute_paid_through()` runs after every payment insert/edit/delete, setting the client's `paid_through_date` to the furthest `extends_through_date` among its remaining payments. This means the dashboard status is always derived from the actual payment history — editing or deleting a stale payment can't leave the client's status wrong.

## API

A read-only JSON endpoint is available for scripting/integrations:

```
GET /api/clients
```

Returns the same serialized client list (including computed status/meter) used by the dashboard.

## Customizing

- **Expiring window / meter scale** — `EXPIRING_WINDOW_DAYS` and `METER_FULL_DAYS` in `db.py`.
- **Currency symbols** — `CURRENCY_SYMBOLS` in `app.py`; unrecognized currency codes fall back to showing the code itself.
- **Port** — hardcoded to `3006` in `app.py`'s `__main__` block and in your gunicorn command; change both if you need a different port.
- **Styling** — everything is in `static/style.css`, no CSS framework or preprocessor involved.

## License

MIT — see [LICENSE](LICENSE).
