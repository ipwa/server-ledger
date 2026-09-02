-- Server Ledger schema (SQLite)

CREATE TABLE IF NOT EXISTS clients (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL,
    domain             TEXT    NOT NULL DEFAULT '',
    monthly_amount     REAL,                       -- NULL for personal/internal
    currency           TEXT    NOT NULL DEFAULT 'USD',
    is_personal        INTEGER NOT NULL DEFAULT 0, -- 0/1
    paid_through_date  TEXT,                       -- ISO date (YYYY-MM-DD), NULL for personal
    notes              TEXT    NOT NULL DEFAULT '',
    archived           INTEGER NOT NULL DEFAULT 0, -- soft delete
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id              INTEGER NOT NULL REFERENCES clients(id),
    amount                 REAL    NOT NULL,
    paid_on_date           TEXT    NOT NULL,       -- ISO date
    extends_from_date      TEXT,                   -- ISO date, NULL if same as prior coverage end
    extends_through_date   TEXT    NOT NULL,       -- ISO date
    created_at             TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payments_client_id ON payments(client_id);
