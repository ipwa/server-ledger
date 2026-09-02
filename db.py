import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "server_ledger.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

STATUS_ORDER = {"overdue": 0, "expiring": 1, "active": 2, "internal": 3}
EXPIRING_WINDOW_DAYS = 7
METER_FULL_DAYS = 30


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn):
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(payments)")}
    if "extends_from_date" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN extends_from_date TEXT")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    _migrate(conn)
    conn.commit()
    conn.close()


def _parse_date(s):
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def compute_status(client, today=None):
    today = today or date.today()
    if client["is_personal"]:
        return "internal", None
    pt = _parse_date(client["paid_through_date"])
    if pt is None:
        return "internal", None
    days_left = (pt - today).days
    if days_left < 0:
        return "overdue", days_left
    if days_left <= EXPIRING_WINDOW_DAYS:
        return "expiring", days_left
    return "active", days_left


def meter_for(status, days_left):
    if status == "internal":
        return {"pct": 0, "label": "—"}
    if status == "overdue":
        return {"pct": 100, "label": f"{abs(days_left)}d overdue"}
    pct = max(0, min(100, round((days_left / METER_FULL_DAYS) * 100)))
    return {"pct": pct, "label": f"{days_left}d left"}


def serialize_client(client, today=None):
    today = today or date.today()
    status, days_left = compute_status(client, today)
    meter = meter_for(status, days_left)
    return {
        "id": client["id"],
        "name": client["name"],
        "domain": client["domain"],
        "monthly_amount": client["monthly_amount"],
        "currency": client["currency"],
        "is_personal": bool(client["is_personal"]),
        "paid_through_date": client["paid_through_date"],
        "notes": client["notes"],
        "status": status,
        "days_left": days_left,
        "meter": meter,
    }


def sort_key(c):
    # soonest paid-through first within each status group;
    # internal clients (no date) sort by name.
    status_rank = STATUS_ORDER[c["status"]]
    if c["status"] == "internal":
        return (status_rank, "", c["name"].lower())
    return (status_rank, c["paid_through_date"] or "", c["name"].lower())


def fetch_clients(include_archived=False, today=None):
    conn = get_db()
    if include_archived:
        rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM clients WHERE archived = 0 ORDER BY name"
        ).fetchall()
    conn.close()
    clients = [serialize_client(r, today) for r in rows]
    clients.sort(key=sort_key)
    return clients


def fetch_client(client_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    conn.close()
    return row


def fetch_payments(client_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM payments WHERE client_id = ? ORDER BY paid_on_date DESC, id DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    return rows


def fetch_payment(payment_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    conn.close()
    return row


def recompute_paid_through(conn, client_id):
    """Set the client's paid_through_date to the furthest coverage among its
    remaining payments, so editing/deleting a payment can't leave it stale."""
    row = conn.execute(
        "SELECT MAX(extends_through_date) AS d FROM payments WHERE client_id = ?",
        (client_id,),
    ).fetchone()
    conn.execute(
        "UPDATE clients SET paid_through_date = ?, updated_at = ? WHERE id = ?",
        (row["d"], datetime.utcnow().isoformat(), client_id),
    )
