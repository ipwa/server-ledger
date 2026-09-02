from datetime import date, datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

import db

app = Flask(__name__)
db.init_db()

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "PEN": "S/ "}


def fmt_money(amount, currency="USD"):
    if amount is None:
        return "—"
    symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{symbol}{amount:,.0f}"


def fmt_money_by_currency(totals):
    """totals: dict currency -> amount. Different currencies can't be
    summed together, so render each as its own figure, joined."""
    if not totals:
        return "—"
    parts = [fmt_money(amount, currency) for currency, amount in sorted(totals.items())]
    return " + ".join(parts)


app.jinja_env.filters["money"] = fmt_money
app.jinja_env.filters["money_multi"] = fmt_money_by_currency


def _sum_by_currency(clients):
    totals = {}
    for c in clients:
        if c["monthly_amount"]:
            totals[c["currency"]] = totals.get(c["currency"], 0) + c["monthly_amount"]
    return totals


def compute_kpis(clients):
    paying = [c for c in clients if not c["is_personal"]]
    overdue = [c for c in paying if c["status"] == "overdue"]
    expiring = [c for c in paying if c["status"] == "expiring"]
    active = [c for c in paying if c["status"] == "active"]
    return {
        "revenue_by_currency": _sum_by_currency(paying),
        "paying_count": len(paying),
        "active_count": len(active),
        "expiring_count": len(expiring),
        "overdue_count": len(overdue),
        "at_risk_by_currency": _sum_by_currency(overdue),
    }


@app.route("/")
def dashboard():
    clients = db.fetch_clients()
    kpis = compute_kpis(clients)
    return render_template(
        "index.html",
        clients=clients,
        kpis=kpis,
        today=date.today().strftime("%Y-%m-%d"),
    )


@app.route("/api/clients")
def api_clients():
    return jsonify(db.fetch_clients())


@app.route("/admin")
def admin():
    clients = db.fetch_clients()
    payments_by_client = {c["id"]: db.fetch_payments(c["id"]) for c in clients}
    return render_template("admin.html", clients=clients, payments_by_client=payments_by_client)


def _wants_json():
    return request.is_json or "application/json" in (request.headers.get("Accept") or "")


def _client_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form


@app.route("/admin/clients", methods=["POST"])
def add_client():
    data = _client_payload()
    name = (data.get("name") or "").strip()
    if not name:
        if _wants_json():
            return jsonify({"error": "name is required"}), 400
        return redirect(url_for("admin"))

    is_personal = str(data.get("is_personal", "")).lower() in ("1", "true", "on", "yes")
    monthly_amount = data.get("monthly_amount") or None
    monthly_amount = float(monthly_amount) if (monthly_amount and not is_personal) else None
    paid_through_date = data.get("paid_through_date") or None
    if is_personal:
        paid_through_date = None

    now = datetime.utcnow().isoformat()
    conn = db.get_db()
    cur = conn.execute(
        """INSERT INTO clients
           (name, domain, monthly_amount, currency, is_personal, paid_through_date,
            notes, archived, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            name,
            (data.get("domain") or "").strip(),
            monthly_amount,
            (data.get("currency") or "USD").strip().upper(),
            1 if is_personal else 0,
            paid_through_date,
            (data.get("notes") or "").strip(),
            now,
            now,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    if _wants_json():
        return jsonify(db.serialize_client(db.fetch_client(new_id))), 201
    return redirect(url_for("admin"))


def _do_edit(client_id, data):
    row = db.fetch_client(client_id)
    if row is None:
        return None
    fields = {
        "name": data.get("name"),
        "domain": data.get("domain"),
        "notes": data.get("notes"),
        "currency": data.get("currency"),
    }
    is_personal_raw = data.get("is_personal")
    is_personal = row["is_personal"]
    if is_personal_raw is not None:
        is_personal = 1 if str(is_personal_raw).lower() in ("1", "true", "on", "yes") else 0

    monthly_amount = row["monthly_amount"]
    if "monthly_amount" in data:
        val = data.get("monthly_amount")
        monthly_amount = float(val) if val not in (None, "") else None
    if is_personal:
        monthly_amount = None

    paid_through_date = row["paid_through_date"]
    if "paid_through_date" in data:
        paid_through_date = data.get("paid_through_date") or None
    if is_personal:
        paid_through_date = None

    conn = db.get_db()
    conn.execute(
        """UPDATE clients SET
             name = ?, domain = ?, notes = ?, currency = ?,
             is_personal = ?, monthly_amount = ?, paid_through_date = ?,
             updated_at = ?
           WHERE id = ?""",
        (
            fields["name"] if fields["name"] is not None else row["name"],
            fields["domain"] if fields["domain"] is not None else row["domain"],
            fields["notes"] if fields["notes"] is not None else row["notes"],
            (fields["currency"] or row["currency"] or "USD").upper(),
            is_personal,
            monthly_amount,
            paid_through_date,
            datetime.utcnow().isoformat(),
            client_id,
        ),
    )
    conn.commit()
    conn.close()
    return db.fetch_client(client_id)


@app.route("/admin/clients/<int:client_id>", methods=["PATCH"])
def edit_client(client_id):
    data = _client_payload()
    updated = _do_edit(client_id, data)
    if updated is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(db.serialize_client(updated))


@app.route("/admin/clients/<int:client_id>/edit", methods=["POST"])
def edit_client_form(client_id):
    _do_edit(client_id, _client_payload())
    return redirect(url_for("admin"))


def _do_payment(client_id, data):
    row = db.fetch_client(client_id)
    if row is None:
        return None
    amount = float(data.get("amount"))
    paid_on_date = data.get("paid_on_date") or date.today().strftime("%Y-%m-%d")
    extends_from_date = data.get("extends_from_date") or None
    extends_through_date = data.get("extends_through_date")
    now = datetime.utcnow().isoformat()

    conn = db.get_db()
    conn.execute(
        """INSERT INTO payments (client_id, amount, paid_on_date, extends_from_date, extends_through_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (client_id, amount, paid_on_date, extends_from_date, extends_through_date, now),
    )
    db.recompute_paid_through(conn, client_id)
    conn.commit()
    conn.close()
    return db.fetch_client(client_id)


@app.route("/admin/clients/<int:client_id>/payment", methods=["POST"])
def record_payment(client_id):
    data = _client_payload()
    updated = _do_payment(client_id, data)
    if updated is None:
        if _wants_json():
            return jsonify({"error": "not found"}), 404
        return redirect(url_for("admin"))
    if _wants_json():
        return jsonify(db.serialize_client(updated)), 201
    return redirect(url_for("admin"))


def _do_edit_payment(payment_id, data):
    row = db.fetch_payment(payment_id)
    if row is None:
        return None

    amount = row["amount"]
    if "amount" in data and data.get("amount") not in (None, ""):
        amount = float(data.get("amount"))
    paid_on_date = data.get("paid_on_date") or row["paid_on_date"]
    extends_from_date = row["extends_from_date"]
    if "extends_from_date" in data:
        extends_from_date = data.get("extends_from_date") or None
    extends_through_date = data.get("extends_through_date") or row["extends_through_date"]

    conn = db.get_db()
    conn.execute(
        """UPDATE payments SET amount = ?, paid_on_date = ?, extends_from_date = ?, extends_through_date = ?
           WHERE id = ?""",
        (amount, paid_on_date, extends_from_date, extends_through_date, payment_id),
    )
    db.recompute_paid_through(conn, row["client_id"])
    conn.commit()
    conn.close()
    return True


@app.route("/admin/payments/<int:payment_id>/edit", methods=["POST"])
def edit_payment_form(payment_id):
    _do_edit_payment(payment_id, _client_payload())
    return redirect(url_for("admin"))


def _do_delete_payment(payment_id):
    row = db.fetch_payment(payment_id)
    if row is None:
        return False
    conn = db.get_db()
    conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    db.recompute_paid_through(conn, row["client_id"])
    conn.commit()
    conn.close()
    return True


@app.route("/admin/payments/<int:payment_id>/delete", methods=["POST"])
def delete_payment_form(payment_id):
    _do_delete_payment(payment_id)
    return redirect(url_for("admin"))


def _do_archive(client_id):
    conn = db.get_db()
    row = conn.execute("SELECT id FROM clients WHERE id = ?", (client_id,)).fetchone()
    if row is None:
        conn.close()
        return False
    conn.execute(
        "UPDATE clients SET archived = 1, updated_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), client_id),
    )
    conn.commit()
    conn.close()
    return True


@app.route("/admin/clients/<int:client_id>", methods=["DELETE"])
def delete_client(client_id):
    ok = _do_archive(client_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"archived": True})


@app.route("/admin/clients/<int:client_id>/archive", methods=["POST"])
def archive_client_form(client_id):
    _do_archive(client_id)
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3006, debug=False)
