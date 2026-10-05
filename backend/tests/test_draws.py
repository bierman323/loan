"""Loans with money drawn over time (e.g. monthly while in school), then repaid."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.database import get_db
from backend.services.projection_engine import (
    LoanSnapshot, LoanSchedule, simulate, get_schedule, add_months, nth_payment_date,
)
from backend.tests.conftest import add_rate

TODAY = date.today()


def days_from_today(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def prime_rate():
    add_rate(days_from_today(-800), 4.45)


def create_school_loan(client, **overrides):
    body = {
        "name": "School",
        "start_date": days_from_today(-60),
        "initial_amount": 2000,
        "payment_frequency": "monthly",
        "spread": 0.5,
        "term_months": 60,
        "planned_draw_amount": 2000,
        "planned_draw_end_date": days_from_today(120),
        "repayment_start_date": days_from_today(180),
    }
    body.update(overrides)
    resp = client.post("/api/loans", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def record(client, loan_id, days_offset, amount):
    resp = client.post("/api/transactions", json={
        "loan_id": loan_id, "date": days_from_today(days_offset), "amount": amount,
    })
    assert resp.status_code == 201, resp.text


class TestSchoolLoan:
    def test_borrowing_phase_estimates_payment_from_projected_balance(self, client):
        loan = create_school_loan(client)
        assert loan["in_borrowing_phase"] is True
        assert loan["total_borrowed"] == 2000
        # Recorded 2000 + 4 planned monthly draws (within the next 120 days) + interest
        assert 10000 < loan["balance_at_repayment_start"] < 10300
        # 60-month payment on ~10.1k at 4.95%
        assert 185 < loan["regular_payment"] < 195
        assert loan["pays_off"] is True
        assert loan["planned_maturity_date"] == add_months(date.fromisoformat(days_from_today(180)), 60).isoformat()
        # The 60th payment pays it off: projected payoff is the planned date
        assert loan["maturity_date"] == loan["planned_maturity_date"]

    def test_recording_a_draw_raises_the_estimated_payment(self, client):
        loan = create_school_loan(client)
        record(client, loan["id"], -1, 5000)  # an unplanned extra draw
        updated = client.get(f"/api/loans/{loan['id']}").json()
        assert updated["total_borrowed"] == 7000
        assert updated["regular_payment"] > loan["regular_payment"] + 80

    def test_no_payments_before_repayment_starts(self, client):
        loan = create_school_loan(client)
        proj = client.post("/api/projections", json={"loan_id": loan["id"]}).json()
        repayment_start = days_from_today(180)
        before = [p["balance"] for p in proj["current_trajectory"] if p["date"] <= repayment_start]
        assert before == sorted(before)  # only grows (draws + interest) until repayment
        assert proj["balance_at_repayment_start"] == pytest.approx(
            client.get(f"/api/loans/{loan['id']}").json()["balance_at_repayment_start"]
        )

    def test_payment_not_due_during_school_even_after_voluntary_payment(self, client):
        loan = create_school_loan(client)
        record(client, loan["id"], -2, -100)
        db = get_db()
        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan["id"],)).fetchone()
        schedule = get_schedule(db, row, TODAY)
        db.close()
        assert schedule.first_payment_date == add_months(date.fromisoformat(days_from_today(180)), 1)

    def test_payment_estimate_freezes_once_repayment_has_started(self, client):
        loan = create_school_loan(client, repayment_start_date=days_from_today(-1))
        assert loan["in_borrowing_phase"] is False
        payment = loan["regular_payment"]
        record(client, loan["id"], 0, 1000)
        assert client.get(f"/api/loans/{loan['id']}").json()["regular_payment"] == payment

    def test_decide_later_no_term_no_payment(self, client):
        loan = create_school_loan(client, term_months=None)
        assert loan["regular_payment"] == 0
        assert loan["maturity_date"] is None
        assert loan["balance_at_repayment_start"] > 10000
        # Setting the term later sizes the payment against the projected balance
        updated = client.patch(f"/api/loans/{loan['id']}", json={"term_months": 48}).json()
        assert updated["regular_payment"] > 200

    def test_changing_draw_plan_resizes_payment(self, client):
        loan = create_school_loan(client)
        updated = client.patch(f"/api/loans/{loan['id']}", json={"planned_draw_amount": 0}).json()
        assert updated["balance_at_repayment_start"] < 2100
        assert updated["regular_payment"] < 45

    def test_repayment_start_cannot_precede_loan_start(self, client):
        resp = client.post("/api/loans", json={
            "name": "X", "start_date": days_from_today(-5), "initial_amount": 100,
            "repayment_start_date": days_from_today(-10),
        })
        assert resp.status_code == 422


class TestRegularLoanPlan:
    def create(self, client, **overrides):
        body = {
            "name": "Car", "start_date": days_from_today(-30), "initial_amount": 30000,
            "payment_frequency": "biweekly", "spread": 0.5, "term_months": 36,
        }
        body.update(overrides)
        resp = client.post("/api/loans", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_term_shift_baseline_survives_payment_change(self, client):
        loan = self.create(client)
        planned = loan["planned_maturity_date"]
        updated = client.patch(f"/api/loans/{loan['id']}", json={"regular_payment": loan["regular_payment"] * 2}).json()
        assert updated["planned_maturity_date"] == planned
        assert updated["term_months"] < 24  # remaining term from today
        assert updated["maturity_date"] < planned  # paying off early

    def test_payment_too_low_never_pays_off(self, client):
        loan = self.create(client, term_months=None, regular_payment=20)
        assert loan["term_months"] is None
        assert loan["pays_off"] is False
        assert loan["maturity_date"] is None
        assert loan["interest_remaining"] is None
        proj = client.post("/api/projections", json={"loan_id": loan["id"], "extra_recurring": 10}).json()
        assert proj["current_pays_off"] is False
        assert proj["interest_saved"] is None
        assert proj["months_saved"] is None

    def test_clearing_term_makes_loan_open_ended(self, client):
        loan = self.create(client)
        updated = client.patch(f"/api/loans/{loan['id']}", json={"term_months": None}).json()
        assert updated["term_months"] is None
        assert updated["planned_maturity_date"] is None
        assert updated["regular_payment"] == loan["regular_payment"]

    def test_cannot_clear_payment(self, client):
        loan = self.create(client)
        assert client.patch(f"/api/loans/{loan['id']}", json={"regular_payment": None}).status_code == 400

    def test_next_payment_follows_last_recorded_payment(self, client):
        loan = self.create(client)
        record(client, loan["id"], -3, -400)
        db = get_db()
        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan["id"],)).fetchone()
        schedule = get_schedule(db, row, TODAY)
        db.close()
        assert schedule.first_payment_date == TODAY + timedelta(days=11)


class TestSimulation:
    def test_carried_interest_is_compounded_at_month_end(self):
        month_end = date(2026, 1, 31)
        snapshot = LoanSnapshot(
            balance=Decimal("1000"), annual_rate=Decimal("0"),
            accrued_this_month=Decimal("10"), today=month_end - timedelta(days=5),
        )
        schedule = LoanSchedule(regular_payment=Decimal("0"), frequency="monthly", first_payment_date=date(2027, 1, 1))
        result = simulate(snapshot, schedule, stop_after=month_end + timedelta(days=1), include_payments=False)
        assert result.balance_on(month_end) == Decimal("1010.00")
        # Interest accrued before today is not counted again as future interest
        assert result.total_interest == 0

    def test_monthly_payments_use_calendar_months(self):
        assert nth_payment_date(date(2026, 1, 31), "monthly", 1) == date(2026, 2, 28)
        assert nth_payment_date(date(2026, 1, 31), "monthly", 2) == date(2026, 3, 31)
        assert nth_payment_date(date(2026, 1, 1), "biweekly", 2) == date(2026, 1, 29)


@pytest.mark.parametrize("frequency", ["weekly", "biweekly", "monthly"])
@pytest.mark.parametrize("repayment_offset_days", [180, 197, 410])  # varied days of the month
def test_estimated_payment_pays_off_exactly_on_plan(client, frequency, repayment_offset_days):
    loan = create_school_loan(
        client, payment_frequency=frequency, repayment_start_date=days_from_today(repayment_offset_days),
        planned_draw_end_date=days_from_today(repayment_offset_days - 30),
    )
    assert loan["pays_off"] is True
    projected = date.fromisoformat(loan["maturity_date"])
    planned = date.fromisoformat(loan["planned_maturity_date"])
    # Weekly/biweekly terms don't land exactly on a calendar month; within one period
    assert abs((projected - planned).days) <= {"weekly": 7, "biweekly": 14, "monthly": 0}[frequency]


class TestSpread:
    def test_new_loan_default_spread_comes_from_config(self, client):
        from backend.config import DEFAULT_SPREAD
        assert client.get("/api/defaults").json() == {"spread": DEFAULT_SPREAD}
        resp = client.post("/api/loans", json={
            "name": "X", "start_date": days_from_today(-5), "initial_amount": 1000, "regular_payment": 50,
        })
        assert resp.json()["spread"] == DEFAULT_SPREAD

    def test_changing_spread_recalculates_all_history(self, client):
        from backend.tests.conftest import balance_rows
        loan = create_school_loan(client, spread=0.9)
        interest_before = loan["interest_paid"]
        payment_before = loan["regular_payment"]
        updated = client.patch(f"/api/loans/{loan['id']}", json={"spread": 0.5}).json()
        assert all(row["effective_rate"] == pytest.approx(4.95) for row in balance_rows(loan["id"]))
        assert updated["interest_paid"] < interest_before
        # Borrowing phase: the estimated payment follows the lower rate
        assert updated["regular_payment"] < payment_before


class TestPlannedDrawSchedule:
    def schedule_for(self, loan_id):
        db = get_db()
        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        schedule = get_schedule(db, row, TODAY)
        db.close()
        return schedule

    def test_planned_draws_follow_regular_draw_day_not_loan_start(self, client):
        # Loan started on one day, but regular draws happen on another (like the 1st)
        loan = create_school_loan(client, start_date=days_from_today(-50), initial_amount=1500,
                                  planned_draw_amount=3000)
        regular_draw_day = TODAY - timedelta(days=3)
        record(client, loan["id"], -3, 3000)
        draw_dates = self.schedule_for(loan["id"]).draw_dates
        # Monthly from the recorded regular draw, with no extra draw on the loan start's day
        expected = [add_months(regular_draw_day, n) for n in range(1, len(draw_dates) + 1)]
        assert draw_dates == expected
        assert len(draw_dates) >= 3

    def test_one_off_draw_of_other_amount_does_not_shift_schedule(self, client):
        loan = create_school_loan(client, planned_draw_amount=2000)
        before = self.schedule_for(loan["id"]).draw_dates
        record(client, loan["id"], -1, 750)  # one-off
        assert self.schedule_for(loan["id"]).draw_dates == before
