from fastapi import APIRouter, HTTPException
from datetime import date
from backend.database import get_db
from backend.models import TransactionCreate, TransactionUpdate, TransactionResponse
from backend.services.interest_engine import recompute_daily_balances
from backend.services.loan_plan import refresh_estimated_payment

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _reject_date_before_loan_start(txn_date: date, loan_start_date: str):
    """Balances are only computed from the loan start, so earlier transactions would be ignored."""
    if txn_date < date.fromisoformat(loan_start_date):
        raise HTTPException(
            status_code=400,
            detail=f"Transaction date cannot be before the loan start date ({loan_start_date})",
        )


@router.get("", response_model=list[TransactionResponse])
def list_transactions(loan_id: int | None = None):
    db = get_db()
    try:
        if loan_id:
            rows = db.execute(
                "SELECT * FROM transactions WHERE loan_id = ? ORDER BY date DESC, id DESC",
                (loan_id,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM transactions ORDER BY date DESC, id DESC"
            ).fetchall()
        return [TransactionResponse(**dict(r)) for r in rows]
    finally:
        db.close()


@router.post("", response_model=TransactionResponse, status_code=201)
def create_transaction(txn: TransactionCreate):
    db = get_db()
    try:
        # Verify loan exists
        loan = db.execute("SELECT id, start_date FROM loans WHERE id = ?", (txn.loan_id,)).fetchone()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")
        _reject_date_before_loan_start(txn.date, loan["start_date"])

        cursor = db.execute(
            "INSERT INTO transactions (loan_id, date, amount, description) VALUES (?, ?, ?, ?)",
            (txn.loan_id, txn.date.isoformat(), txn.amount, txn.description),
        )
        db.commit()
        txn_id = cursor.lastrowid

        # Recompute from transaction date forward
        recompute_daily_balances(txn.loan_id, from_date=txn.date)
        refresh_estimated_payment(txn.loan_id)

        row = db.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        return TransactionResponse(**dict(row))
    finally:
        db.close()


@router.patch("/{txn_id}", response_model=TransactionResponse)
def update_transaction(txn_id: int, update: TransactionUpdate):
    db = get_db()
    try:
        existing = db.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Transaction not found")

        updates = update.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Convert date to string if present
        if "date" in updates:
            loan = db.execute("SELECT start_date FROM loans WHERE id = ?", (existing["loan_id"],)).fetchone()
            _reject_date_before_loan_start(updates["date"], loan["start_date"])
            updates["date"] = updates["date"].isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        values.append(txn_id)
        db.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", values)
        db.commit()

        # Recompute from the earliest affected date
        earliest = min(
            date.fromisoformat(existing["date"]),
            date.fromisoformat(updates.get("date", existing["date"])),
        )
        recompute_daily_balances(existing["loan_id"], from_date=earliest)
        refresh_estimated_payment(existing["loan_id"])

        row = db.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        return TransactionResponse(**dict(row))
    finally:
        db.close()


@router.delete("/{txn_id}", status_code=204)
def delete_transaction(txn_id: int):
    db = get_db()
    try:
        existing = db.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Transaction not found")

        loan_id = existing["loan_id"]
        txn_date = date.fromisoformat(existing["date"])

        db.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
        db.commit()

        recompute_daily_balances(loan_id, from_date=txn_date)
        refresh_estimated_payment(loan_id)
    finally:
        db.close()
