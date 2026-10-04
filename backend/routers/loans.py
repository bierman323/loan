from datetime import date
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from backend.database import get_db
from backend.models import LoanCreate, LoanUpdate, LoanResponse
from backend.services.interest_engine import recompute_daily_balances, get_current_balance
from backend.services.projection_engine import project_payoff, add_months
from backend.services.loan_plan import (
    payment_for_term,
    term_for_payment,
    is_in_borrowing_phase,
    principal_for_plan,
    planned_maturity_for_term,
    refresh_estimated_payment,
)

router = APIRouter(prefix="/api/loans", tags=["loans"])

# Loan columns that cannot be cleared by sending null in a PATCH
NON_NULLABLE_UPDATE_FIELDS = {"name", "regular_payment", "payment_frequency", "spread", "planned_draw_amount"}


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
    """Add computed fields (balance, interest paid, interest remaining, borrowing plan) to a loan dict."""
    loan_id = loan["id"]
    bal = get_current_balance(loan_id)
    if bal:
        loan["current_balance"] = bal["closing_balance"]
        loan["daily_interest"] = bal["interest_accrued"]
        loan["effective_rate"] = bal["effective_rate"]

    db = get_db()
    try:
        # Interest paid to date: sum of all daily interest accrued
        row = db.execute(
            "SELECT COALESCE(SUM(interest_accrued), 0) as total FROM daily_balances WHERE loan_id = ?",
            (loan_id,),
        ).fetchone()
        loan["interest_paid"] = round(row["total"], 2) if row else 0

        # Money out (draws, including the initial disbursement) and money back (payments)
        totals = db.execute(
            """SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS borrowed,
                      COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0) AS repaid
               FROM transactions WHERE loan_id = ? AND date <= ?""",
            (loan_id, date.today().isoformat()),
        ).fetchone()
        loan["total_borrowed"] = round(totals["borrowed"], 2)
        loan["total_repaid"] = round(totals["repaid"], 2)
    finally:
        db.close()

    loan["in_borrowing_phase"] = is_in_borrowing_phase(loan)

    # Project forward: payoff date, remaining interest, balance when repayment begins
    proj = project_payoff(loan_id)
    loan["balance_at_repayment_start"] = proj.get("balance_at_repayment_start")
    if loan.get("regular_payment") and loan["regular_payment"] > 0:
        loan["pays_off"] = proj.get("current_pays_off")
        loan["maturity_date"] = proj.get("current_payoff_date")
        # Remaining interest is only meaningful if the loan actually gets paid off
        if loan["pays_off"]:
            loan["interest_remaining"] = round(proj.get("current_total_interest", 0), 2)
        else:
            loan["interest_remaining"] = None
    else:
        loan["pays_off"] = None
        loan["interest_remaining"] = None
        loan["maturity_date"] = None

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
    db = get_db()
    try:
        cursor = db.execute(
            """INSERT INTO loans (name, start_date, initial_amount, regular_payment, payment_frequency, spread,
                                  term_months, user_id, planned_draw_amount, planned_draw_end_date, repayment_start_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                loan.name, loan.start_date.isoformat(), loan.initial_amount,
                loan.regular_payment, loan.payment_frequency, loan.spread, loan.term_months, user_id,
                loan.planned_draw_amount,
                loan.planned_draw_end_date.isoformat() if loan.planned_draw_end_date else None,
                loan.repayment_start_date.isoformat() if loan.repayment_start_date else None,
            ),
        )
        loan_id = cursor.lastrowid

        # Add initial disbursement as a transaction
        db.execute(
            "INSERT INTO transactions (loan_id, date, amount, description) VALUES (?, ?, ?, ?)",
            (loan_id, loan.start_date.isoformat(), loan.initial_amount, "Initial disbursement"),
        )
        db.commit()

        # Compute initial balances (needed before projecting the balance at repayment start)
        recompute_daily_balances(loan_id)

        # Calculate missing payment or term.
        # Borrowing phase: size against the projected balance when repayment begins.
        # Otherwise: size against the amount borrowed, counted from repayment start / loan start.
        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if is_in_borrowing_phase(row):
            principal = principal_for_plan(row)
            basis_date = loan.repayment_start_date
        else:
            principal = loan.initial_amount
            basis_date = loan.repayment_start_date or loan.start_date
        payment, term = _resolve_payment_and_term(
            principal, loan.regular_payment, loan.term_months, loan.payment_frequency, loan.spread,
        )
        planned_maturity = add_months(basis_date, term).isoformat() if term else None
        db.execute(
            "UPDATE loans SET regular_payment = ?, term_months = ?, planned_maturity_date = ? WHERE id = ?",
            (payment, term, planned_maturity, loan_id),
        )
        db.commit()

        # During the borrowing phase, replace the formula estimate with the exact payment
        refresh_estimated_payment(loan_id)

        row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
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

        updates = update.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        for field_name in NON_NULLABLE_UPDATE_FIELDS:
            if field_name in updates and updates[field_name] is None:
                raise HTTPException(status_code=400, detail=f"{field_name} cannot be cleared")

        start_date = date.fromisoformat(existing["start_date"])
        for field_name in ("repayment_start_date", "planned_draw_end_date"):
            if updates.get(field_name) is not None:
                if updates[field_name] < start_date:
                    raise HTTPException(status_code=400, detail=f"{field_name} cannot be before the loan start date")
                updates[field_name] = updates[field_name].isoformat()

        # Step 1: save everything except payment/term, so the payment/term math below sees
        # the new rate spread, frequency, draw plan and repayment start.
        payment_term_fields = {"regular_payment", "term_months"}
        plan_updates = {k: v for k, v in updates.items() if k not in payment_term_fields}
        if plan_updates:
            set_clause = ", ".join(f"{k} = ?" for k in plan_updates)
            db.execute(f"UPDATE loans SET {set_clause} WHERE id = ?", [*plan_updates.values(), loan_id])
            db.commit()
        if "spread" in updates:
            recompute_daily_balances(loan_id)

        # Step 2: if payment, term, or frequency changed, recalculate the other from the
        # balance the plan is sized against (projected balance at repayment start during
        # the borrowing phase, otherwise the current balance).
        loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        frequency = loan["payment_frequency"]
        spread = loan["spread"]
        new_payment = updates.get("regular_payment", loan["regular_payment"])
        new_term = updates.get("term_months", loan["term_months"])
        new_planned_maturity = loan["planned_maturity_date"]

        payment_changed = "regular_payment" in updates
        term_changed = "term_months" in updates
        frequency_changed = "payment_frequency" in updates
        repayment_start_changed = "repayment_start_date" in updates

        if payment_changed and not term_changed:
            # Payment changed → recalculate remaining term
            new_term = term_for_payment(principal_for_plan(loan), new_payment, frequency, spread)
            # Before repayment begins any change is a re-plan; afterwards the planned
            # maturity stays put so the dashboard can show the effect of the new payment.
            if is_in_borrowing_phase(loan):
                new_planned_maturity = planned_maturity_for_term(loan, new_term) if new_term else None
        elif term_changed and not payment_changed:
            if new_term:
                # Term changed → recalculate payment; the new term is the new plan
                new_payment = payment_for_term(principal_for_plan(loan), new_term, frequency, spread)
                new_planned_maturity = planned_maturity_for_term(loan, new_term)
            else:
                # Term cleared → open-ended, keep the current payment
                new_planned_maturity = None
        elif payment_changed and term_changed:
            new_planned_maturity = planned_maturity_for_term(loan, new_term) if new_term else None
        elif frequency_changed and new_term:
            # Frequency changed alone → recalculate payment keeping term fixed
            new_payment = payment_for_term(principal_for_plan(loan), new_term, frequency, spread)
        elif repayment_start_changed and new_term:
            # Repayment moved → the planned payoff moves with it
            new_planned_maturity = planned_maturity_for_term(loan, new_term)

        db.execute(
            "UPDATE loans SET regular_payment = ?, term_months = ?, planned_maturity_date = ? WHERE id = ?",
            (new_payment, new_term, new_planned_maturity, loan_id),
        )
        db.commit()

        # During the borrowing phase the payment follows the projected balance
        refresh_estimated_payment(loan_id)

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


def _resolve_payment_and_term(
    principal: float, payment: float, term_months: int | None,
    frequency: str, spread: float,
) -> tuple[float, int | None]:
    """
    If term is given but payment is 0 → calculate payment from term.
    If payment is given but term is None → calculate term from payment.
    Uses current prime rate + spread for the calculation.
    """
    if term_months and (not payment or payment <= 0):
        return payment_for_term(principal, term_months, frequency, spread), term_months

    if payment and payment > 0 and not term_months:
        return payment, term_for_payment(principal, payment, frequency, spread)

    return payment, term_months
