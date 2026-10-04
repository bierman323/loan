"""Regression tests for the issues found in the code review."""
import asyncio
from datetime import date, timedelta

import pytest

import backend.services.rate_fetcher as rate_fetcher
from backend.services.interest_engine import recompute_daily_balances
from backend.tests.conftest import add_rate, rate_rows, balance_rows


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def create_loan(client, **overrides):
    body = {
        "name": "Test",
        "start_date": days_ago(20),
        "initial_amount": 10000,
        "regular_payment": 200,
        "payment_frequency": "biweekly",
        "spread": 0.5,
    }
    body.update(overrides)
    resp = client.post("/api/loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Static file serving ---

class TestStaticServing:
    def test_path_traversal_does_not_leak_files(self, client):
        from backend import main
        if not main.os.path.isdir(main.static_dir):
            pytest.skip("static/ not built")
        resp = client.get("/..%2fbackend%2fconfig.py")
        assert "DATABASE_PATH" not in resp.text
        resp = client.get("/..%2fdata%2floan_tracker.db")
        assert not resp.content.startswith(b"SQLite format")

    def test_unknown_api_route_is_404(self, client):
        from backend import main
        if not main.os.path.isdir(main.static_dir):
            pytest.skip("static/ not built")
        assert client.get("/api/does-not-exist").status_code == 404


# --- Rates ---

class TestRateSync:
    def fake_observations(self, monkeypatch, observations):
        async def fake_fetch(start_date):
            return [(date.fromisoformat(d), r) for d, r in observations if date.fromisoformat(d) >= start_date]
        monkeypatch.setattr(rate_fetcher, "fetch_prime_rate_observations", fake_fetch)

    def test_stores_observation_dates_and_only_changes(self, monkeypatch):
        self.fake_observations(monkeypatch, [
            ("2026-01-07", 4.70), ("2026-01-14", 4.70), ("2026-01-21", 4.45), ("2026-01-28", 4.45),
        ])
        inserted = asyncio.run(rate_fetcher.sync_rate_history(date(2026, 1, 10)))
        assert inserted == date(2026, 1, 7)
        assert rate_rows() == [
            ("2026-01-07", 4.70, "bank_of_canada_api"),
            ("2026-01-21", 4.45, "bank_of_canada_api"),
        ]
        # Syncing again adds nothing
        assert asyncio.run(rate_fetcher.sync_rate_history(date(2026, 1, 10))) is None
        assert len(rate_rows()) == 2

    def test_removes_existing_duplicate_api_rows_but_keeps_manual(self, monkeypatch):
        add_rate("2026-03-14", 4.45, "bank_of_canada_api")
        add_rate("2026-03-15", 4.45, "bank_of_canada_api")
        add_rate("2026-03-16", 4.45, "manual")
        add_rate("2026-03-21", 4.45, "bank_of_canada_api")
        self.fake_observations(monkeypatch, [("2026-03-11", 4.45), ("2026-03-18", 4.45)])
        asyncio.run(rate_fetcher.sync_rate_history(date(2026, 3, 13)))
        assert rate_rows() == [
            ("2026-03-11", 4.45, "bank_of_canada_api"),
            ("2026-03-16", 4.45, "manual"),
        ]

    def test_api_failure_changes_nothing(self, monkeypatch):
        add_rate("2026-03-14", 4.45)
        async def failing_fetch(start_date):
            return None
        monkeypatch.setattr(rate_fetcher, "fetch_prime_rate_observations", failing_fetch)
        assert asyncio.run(rate_fetcher.sync_rate_history(date(2026, 1, 1))) is None
        assert rate_rows() == [("2026-03-14", 4.45, "manual")]


# --- Interest engine ---

class TestInterestEngine:
    def test_days_before_first_rate_use_earliest_rate_not_spread_only(self, client):
        add_rate(days_ago(5), 4.45)
        loan = create_loan(client, start_date=days_ago(10), spread=0.5)
        rows = balance_rows(loan["id"])
        assert rows[0]["effective_rate"] == pytest.approx(4.95)

    def test_partial_recompute_matches_full_recompute(self, client):
        add_rate(days_ago(400), 4.45)
        loan = create_loan(client, start_date=days_ago(90))
        client.post("/api/transactions", json={"loan_id": loan["id"], "date": days_ago(45), "amount": -500})
        partial = balance_rows(loan["id"])
        recompute_daily_balances(loan["id"])
        assert balance_rows(loan["id"]) == partial

    def test_partial_recompute_with_stale_cache_does_not_skip_days(self, client):
        add_rate(days_ago(400), 4.45)
        loan = create_loan(client, start_date=days_ago(60))
        # Simulate server downtime: cache stops 30 days ago
        from backend.database import get_db
        db = get_db()
        db.execute("DELETE FROM daily_balances WHERE loan_id = ? AND date > ?", (loan["id"], days_ago(30)))
        db.commit()
        db.close()
        recompute_daily_balances(loan["id"], from_date=date.today())
        dates = [r["date"] for r in balance_rows(loan["id"])]
        assert len(dates) == 61  # start date through today, no gaps
        assert dates[-1] == date.today().isoformat()


# --- Transactions & users ---

class TestValidation:
    def test_transaction_before_loan_start_rejected(self, client):
        add_rate(days_ago(400), 4.45)
        loan = create_loan(client, start_date=days_ago(10))
        resp = client.post("/api/transactions", json={"loan_id": loan["id"], "date": days_ago(11), "amount": -100})
        assert resp.status_code == 400
        assert "before the loan start" in resp.json()["detail"]

    def test_zero_amount_rejected(self, client):
        add_rate(days_ago(400), 4.45)
        loan = create_loan(client)
        resp = client.post("/api/transactions", json={"loan_id": loan["id"], "date": days_ago(1), "amount": 0})
        assert resp.status_code == 422

    def test_unknown_frequency_rejected(self, client):
        resp = client.post("/api/loans", json={
            "name": "X", "start_date": days_ago(1), "initial_amount": 100, "payment_frequency": "daily",
        })
        assert resp.status_code == 422

    def test_delete_user_with_loans_is_409_not_500(self, client):
        add_rate(days_ago(400), 4.45)
        user = client.post("/api/users", json={"name": "Wife"}).json()
        client.post("/api/loans", headers={"X-User-Token": user["token"]}, json={
            "name": "School", "start_date": days_ago(5), "initial_amount": 1000, "regular_payment": 50,
        })
        resp = client.delete(f"/api/users/{user['id']}")
        assert resp.status_code == 409


def test_duplicate_cleanup_runs_even_when_api_is_down(monkeypatch):
    add_rate("2026-03-14", 4.45, "bank_of_canada_api")
    add_rate("2026-03-15", 4.45, "bank_of_canada_api")
    async def failing_fetch(start_date):
        return None
    monkeypatch.setattr(rate_fetcher, "fetch_prime_rate_observations", failing_fetch)
    asyncio.run(rate_fetcher.sync_rate_history(date(2026, 1, 1)))
    assert rate_rows() == [("2026-03-14", 4.45, "bank_of_canada_api")]
