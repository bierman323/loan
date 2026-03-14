import sqlite3
import os
from backend.config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_date DATE NOT NULL,
    initial_amount REAL NOT NULL,
    regular_payment REAL NOT NULL DEFAULT 0,
    payment_frequency TEXT NOT NULL DEFAULT 'biweekly',
    spread REAL NOT NULL DEFAULT 0.9,
    term_months INTEGER,
    user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    amount REAL NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rate_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    effective_date DATE NOT NULL,
    prime_rate REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_balances (
    loan_id INTEGER NOT NULL,
    date DATE NOT NULL,
    opening_balance REAL NOT NULL,
    interest_accrued REAL NOT NULL,
    closing_balance REAL NOT NULL,
    effective_rate REAL NOT NULL,
    PRIMARY KEY (loan_id, date)
);

CREATE INDEX IF NOT EXISTS idx_transactions_loan_date ON transactions(loan_id, date);
CREATE INDEX IF NOT EXISTS idx_rate_history_date ON rate_history(effective_date);
CREATE INDEX IF NOT EXISTS idx_daily_balances_loan_date ON daily_balances(loan_id, date);
"""


def get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    # Migrations for existing databases
    cols = [row[1] for row in conn.execute("PRAGMA table_info(loans)").fetchall()]
    if "term_months" not in cols:
        conn.execute("ALTER TABLE loans ADD COLUMN term_months INTEGER")
    if "user_id" not in cols:
        conn.execute("ALTER TABLE loans ADD COLUMN user_id INTEGER REFERENCES users(id)")
    conn.commit()
    conn.close()
