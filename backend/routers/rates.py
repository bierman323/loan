from fastapi import APIRouter, HTTPException
from backend.database import get_db
from backend.models import RateCreate, RateResponse
from backend.services.interest_engine import recompute_daily_balances

router = APIRouter(prefix="/api/rates", tags=["rates"])


@router.get("", response_model=list[RateResponse])
def list_rates():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM rate_history ORDER BY effective_date DESC"
        ).fetchall()
        return [RateResponse(**dict(r)) for r in rows]
    finally:
        db.close()


@router.post("", response_model=RateResponse, status_code=201)
def create_rate(rate: RateCreate):
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO rate_history (effective_date, prime_rate, source) VALUES (?, ?, ?)",
            (rate.effective_date.isoformat(), rate.prime_rate, rate.source),
        )
        db.commit()
        rate_id = cursor.lastrowid

        # Recompute all loans from the effective date forward
        loans = db.execute("SELECT id FROM loans").fetchall()
        for loan in loans:
            recompute_daily_balances(loan["id"], from_date=rate.effective_date)

        row = db.execute("SELECT * FROM rate_history WHERE id = ?", (rate_id,)).fetchone()
        return RateResponse(**dict(row))
    finally:
        db.close()


@router.delete("/{rate_id}", status_code=204)
def delete_rate(rate_id: int):
    db = get_db()
    try:
        existing = db.execute("SELECT * FROM rate_history WHERE id = ?", (rate_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Rate not found")

        from datetime import date as date_type
        eff_date = date_type.fromisoformat(existing["effective_date"])

        db.execute("DELETE FROM rate_history WHERE id = ?", (rate_id,))
        db.commit()

        # Recompute all loans
        loans = db.execute("SELECT id FROM loans").fetchall()
        for loan in loans:
            recompute_daily_balances(loan["id"], from_date=eff_date)
    finally:
        db.close()
