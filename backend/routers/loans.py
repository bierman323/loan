import math
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from backend.database import get_db
from backend.models import LoanCreate, LoanUpdate, LoanResponse
from backend.services.interest_engine import recompute_daily_balances, get_current_balance
from backend.services.rate_fetcher import get_latest_rate
from backend.services.projection_engine import project_payoff

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _get_user_id(token: str | None) -> int | None:
    if not token:
        return None
    db = get_db()
    try:
        row = db.execute("SELECT id FROM users WHERE token = ?", (token,)).fetchone()
        return row["id"] if row else None
    finally:
        db.close()


def _enrich_loan(loan: dict) -> dict:
    """Add computed fields (balance, interest paid, interest remaining) to a loan dict."""
    loan_id = loan["id"]
    bal = get_current_balance(loan_id)
    if bal:
        loan["current_balance"] = bal["closing_balance"]
        loan["daily_interest"] = bal["interest_accrued"]
        loan["effective_rate"] = bal["effective_rate"]

    # Interest paid to date: sum of all daily interest accrued
    db = get_db()
    try:
        row = db.execute(
            "SELECT COALESCE(SUM(interest_accrued), 0) as total FROM daily_balances WHERE loan_id = ?",
            (loan_id,),
        ).fetchone()
        loan["interest_paid"] = round(row["total"], 2) if row else 0
    finally:
        db.close()

    # Interest remaining: project forward to payoff
    if loan.get("regular_payment") and loan["regular_payment"] > 0:
        proj = project_payoff(loan_id)
        loan["interest_remaining"] = round(proj.get("current_total_interest", 0), 2)
    else:
        loan["interest_remaining"] = None

    return loan


@router.get("", response_model=list[LoanResponse])
def list_loans(x_user_token: Optional[str] = Header(None)):
    user_id = _get_user_id(x_user_token)
    db = get_db()
    try:
        if user_id:
            rows = db.execute("SELECT * FROM loans WHERE user_id = ? ORDER BY created_at", (user_id,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM loans WHERE user_id IS NULL ORDER BY created_at").fetchall()
        return [LoanResponse(**_enrich_loan(dict(row))) for row in rows]
    finally:
        db.close()


@router.post("", response_model=LoanResponse, status_code=201)
def create_loan(loan: LoanCreate, x_user_token: Optional[str] = Header(None)):
    user_id = _get_user_id(x_user_token)
    # Calculate missing payment or term
    payment, term = _resolve_payment_and_term(
        loan.initial_amount, loan.regular_payment, loan.term_months,
        loan.payment_frequency, loan.spread,
    )
    db = get_db()
    try:
        cursor = db.execute(
            """INSERT INTO loans (name, start_date, initial_amount, regular_payment, payment_frequency, spread, term_months, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (loan.name, loan.start_date.isoformat(), loan.initial_amount,
             payment, loan.payment_frequency, loan.spread, term, user_id),
        )
        db.commit()
        loan_id = cursor.lastrowid
        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()

        # Add initial disbursement as a transaction
        db.execute(
            "INSERT INTO transactions (loan_id, date, amount, description) VALUES (?, ?, ?, ?)",
            (loan_id, loan.start_date.isoformat(), loan.initial_amount, "Initial disbursement"),
        )
        db.commit()

        # Compute initial balances
        recompute_daily_balances(loan_id)

        return LoanResponse(**_enrich_loan(dict(row)))
    finally:
        db.close()


@router.get("/{loan_id}", response_model=LoanResponse)
def get_loan(loan_id: int):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Loan not found")
        return LoanResponse(**_enrich_loan(dict(row)))
    finally:
        db.close()


@router.patch("/{loan_id}", response_model=LoanResponse)
def update_loan(loan_id: int, update: LoanUpdate):
    db = get_db()
    try:
        existing = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Loan not found")

        updates = update.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # If payment or term changed, recalculate the other from current balance
        if "regular_payment" in updates or "term_months" in updates:
            bal = get_current_balance(loan_id)
            current_balance = bal["closing_balance"] if bal else existing["initial_amount"]
            frequency = updates.get("payment_frequency", existing["payment_frequency"])
            spread = updates.get("spread", existing["spread"])

            new_payment = updates.get("regular_payment", existing["regular_payment"])
            new_term = updates.get("term_months", existing["term_months"])

            if "regular_payment" in updates and "term_months" not in updates:
                # Payment changed → recalculate remaining term from current balance
                _, recalc_term = _resolve_payment_and_term(
                    current_balance, new_payment, None, frequency, spread,
                )
                updates["term_months"] = recalc_term
            elif "term_months" in updates and "regular_payment" not in updates:
                # Term changed → recalculate payment from current balance
                recalc_payment, _ = _resolve_payment_and_term(
                    current_balance, 0, new_term, frequency, spread,
                )
                updates["regular_payment"] = recalc_payment

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        values.append(loan_id)
        db.execute(f"UPDATE loans SET {set_clause} WHERE id = ?", values)
        db.commit()

        # Recompute if spread changed
        if "spread" in updates:
            recompute_daily_balances(loan_id)

        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        return LoanResponse(**_enrich_loan(dict(row)))
    finally:
        db.close()


@router.delete("/{loan_id}", status_code=204)
def delete_loan(loan_id: int):
    db = get_db()
    try:
        db.execute("DELETE FROM daily_balances WHERE loan_id = ?", (loan_id,))
        db.execute("DELETE FROM transactions WHERE loan_id = ?", (loan_id,))
        db.execute("DELETE FROM loans WHERE id = ?", (loan_id,))
        db.commit()
    finally:
        db.close()


@router.get("/{loan_id}/balances", response_model=list[dict])
def get_balance_history(loan_id: int):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM daily_balances WHERE loan_id = ? ORDER BY date",
            (loan_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def _periods_per_year(frequency: str) -> float:
    return {"weekly": 52, "biweekly": 26, "monthly": 12}.get(frequency, 26)


def _resolve_payment_and_term(
    principal: float, payment: float, term_months: int | None,
    frequency: str, spread: float,
) -> tuple[float, int | None]:
    """
    If term is given but payment is 0 → calculate payment from term.
    If payment is given but term is None → calculate term from payment.
    Uses current prime rate + spread for the calculation.
    """
    prime = get_latest_rate() or 0
    annual_rate = (prime + spread) / 100
    periods_yr = _periods_per_year(frequency)
    r = annual_rate / periods_yr  # rate per payment period

    if term_months and (not payment or payment <= 0):
        # Calculate payment from term
        n = term_months * periods_yr / 12  # total number of payments
        if r > 0 and n > 0:
            payment = principal * r / (1 - (1 + r) ** -n)
            payment = round(payment, 2)
        elif n > 0:
            payment = round(principal / n, 2)
        return payment, term_months

    if payment and payment > 0 and not term_months:
        # Calculate term from payment
        if r > 0 and payment > principal * r:
            n = -math.log(1 - principal * r / payment) / math.log(1 + r)
            term_months = round(n * 12 / periods_yr)
        elif r == 0 and payment > 0:
            n = principal / payment
            term_months = round(n * 12 / periods_yr)
        return payment, term_months

    return payment, term_months
