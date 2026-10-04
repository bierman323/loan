"""
Payment / term math and the borrowing-phase payment estimate.

A loan can have a borrowing phase (e.g. drawing money each month while in school) that
ends at repayment_start_date. Nothing is paid during that phase. The first regular
payment is one period after repayment_start_date, so the payment is sized to amortize the
projected balance at repayment_start_date over term_months.
"""
import math
from datetime import date
from backend.database import get_db
from backend.services.rate_fetcher import get_latest_rate
from backend.services.projection_engine import projected_balance_at, add_months, exact_payment_for_term


def periods_per_year(frequency: str) -> int:
    return {"weekly": 52, "biweekly": 26, "monthly": 12}.get(frequency, 26)


def _rate_per_period(frequency: str, spread: float) -> float:
    prime = get_latest_rate() or 0
    annual_rate = (prime + spread) / 100
    return annual_rate / periods_per_year(frequency)


def payment_for_term(principal: float, term_months: int, frequency: str, spread: float) -> float:
    """Level payment that pays off principal over term_months at current prime + spread."""
    r = _rate_per_period(frequency, spread)
    n = term_months * periods_per_year(frequency) / 12  # total number of payments
    if n <= 0:
        return 0
    if r > 0:
        return round(principal * r / (1 - (1 + r) ** -n), 2)
    return round(principal / n, 2)


def term_for_payment(principal: float, payment: float, frequency: str, spread: float) -> int | None:
    """Months to pay off principal at this payment, or None if the payment never pays it off."""
    if payment <= 0:
        return None
    if principal <= 0:
        return 0
    r = _rate_per_period(frequency, spread)
    periods_yr = periods_per_year(frequency)
    if r > 0:
        if payment <= principal * r:
            return None  # payment does not even cover the interest
        n = -math.log(1 - principal * r / payment) / math.log(1 + r)
    else:
        n = principal / payment
    return round(n * 12 / periods_yr)


def is_in_borrowing_phase(loan) -> bool:
    repayment_start = loan["repayment_start_date"]
    return bool(repayment_start) and date.fromisoformat(repayment_start) > date.today()


def plan_basis_date(loan) -> date:
    """The date the term is counted from: when repayment begins, or today if it already has."""
    if is_in_borrowing_phase(loan):
        return date.fromisoformat(loan["repayment_start_date"])
    return date.today()


def principal_for_plan(loan) -> float:
    """
    The balance the payment/term is sized against: the projected balance when repayment
    begins (borrowing phase), otherwise the current balance.
    """
    balance = projected_balance_at(loan["id"], plan_basis_date(loan))
    if balance is None:
        return loan["initial_amount"]
    return balance


def planned_maturity_for_term(loan, term_months: int) -> str:
    return add_months(plan_basis_date(loan), term_months).isoformat()


def refresh_estimated_payment(loan_id: int) -> None:
    """
    During the borrowing phase the payment is an estimate: re-size it from the term
    whenever the projected balance at repayment start can have changed (new draws,
    rate changes, plan edits, daily interest). Once repayment begins it stays fixed.
    """
    db = get_db()
    try:
        loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not loan or not loan["term_months"] or not is_in_borrowing_phase(loan):
            return
        formula_payment = payment_for_term(
            principal_for_plan(loan), loan["term_months"], loan["payment_frequency"], loan["spread"],
        )
        exact_payment = exact_payment_for_term(
            loan_id, loan["term_months"], periods_per_year(loan["payment_frequency"]), formula_payment,
        )
        payment = exact_payment if exact_payment is not None else formula_payment
        db.execute("UPDATE loans SET regular_payment = ? WHERE id = ?", (payment, loan_id))
        db.commit()
    finally:
        db.close()


def refresh_all_estimated_payments() -> None:
    db = get_db()
    try:
        loan_ids = [row["id"] for row in db.execute("SELECT id FROM loans").fetchall()]
    finally:
        db.close()
    for loan_id in loan_ids:
        refresh_estimated_payment(loan_id)
