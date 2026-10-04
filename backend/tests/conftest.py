import pytest
from fastapi.testclient import TestClient

import backend.database
from backend.database import init_db, get_db


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite database."""
    monkeypatch.setattr(backend.database, "DATABASE_PATH", str(tmp_path / "test.db"))
    init_db()
    yield


@pytest.fixture
def client():
    # Not used as a context manager, so the app lifespan (network rate sync, scheduler) does not run
    from backend.main import app
    return TestClient(app)


def add_rate(effective_date: str, prime_rate: float, source: str = "manual"):
    db = get_db()
    db.execute(
        "INSERT INTO rate_history (effective_date, prime_rate, source) VALUES (?, ?, ?)",
        (effective_date, prime_rate, source),
    )
    db.commit()
    db.close()


def rate_rows() -> list[tuple[str, float, str]]:
    db = get_db()
    rows = db.execute(
        "SELECT effective_date, prime_rate, source FROM rate_history ORDER BY effective_date, id"
    ).fetchall()
    db.close()
    return [(r["effective_date"], r["prime_rate"], r["source"]) for r in rows]


def balance_rows(loan_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM daily_balances WHERE loan_id = ? ORDER BY date", (loan_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
