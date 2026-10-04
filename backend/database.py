import sqlite3
import os
from backend.config import DATABASE_PATH, DEFAULT_SPREAD

SCHEMA = f"""
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
    spread REAL NOT NULL DEFAULT {DEFAULT_SPREAD},
    term_months INTEGER,
    user_id INTEGER REFERENCES users(id),
    planned_draw_amount REAL NOT NULL DEFAULT 0,
    planned_draw_end_date DATE,
    repayment_start_date DATE,
    planned_maturity_date DATE,
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
    # Draws over time: planned monthly borrowing (projection only) and when repayment begins
    if "planned_draw_amount" not in cols:
        conn.execute("ALTER TABLE loans ADD COLUMN planned_draw_amount REAL NOT NULL DEFAULT 0")
    if "planned_draw_end_date" not in cols:
        conn.execute("ALTER TABLE loans ADD COLUMN planned_draw_end_date DATE")
    if "repayment_start_date" not in cols:
        conn.execute("ALTER TABLE loans ADD COLUMN repayment_start_date DATE")
    # The payoff date the plan aims for. term_months is overwritten with the remaining
    # term when the payment is adjusted, so it cannot serve as the baseline.
    if "planned_maturity_date" not in cols:
        conn.execute("ALTER TABLE loans ADD COLUMN planned_maturity_date DATE")
        conn.execute(
            """UPDATE loans SET planned_maturity_date = date(start_date, '+' || term_months || ' months')
               WHERE term_months IS NOT NULL"""
        )
    conn.commit()
    conn.close()
