from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
import calendar
from backend.database import get_db


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def recompute_daily_balances(loan_id: int, from_date: date | None = None):
    """
    Recompute daily balance records for a loan from from_date forward.

    Interest model:
    - Daily accrual: balance × (prime + spread) / 100 / 365
    - Monthly compounding: accumulated daily interest added to principal on last day of month
    """
    db = get_db()
    try:
        loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not loan:
            return

        start_date = date.fromisoformat(loan["start_date"])
        if from_date and from_date > start_date:
            # Get balance from the day before from_date
            prev = db.execute(
                "SELECT closing_balance FROM daily_balances WHERE loan_id = ? AND date < ? ORDER BY date DESC LIMIT 1",
                (loan_id, from_date.isoformat()),
            ).fetchone()
            if prev:
                current_balance = _to_decimal(prev["closing_balance"])
            else:
                current_balance = _to_decimal(loan["initial_amount"])
            calc_start = from_date
        else:
            current_balance = Decimal("0")
            calc_start = start_date
            from_date = start_date

        # Clear existing records from calc_start forward
        db.execute(
            "DELETE FROM daily_balances WHERE loan_id = ? AND date >= ?",
            (loan_id, calc_start.isoformat()),
        )

        # Get all transactions for this loan from calc_start forward
        txn_rows = db.execute(
            "SELECT date, amount FROM transactions WHERE loan_id = ? AND date >= ? ORDER BY date, id",
            (loan_id, calc_start.isoformat()),
        ).fetchall()
        txn_by_date: dict[str, list[Decimal]] = {}
        for t in txn_rows:
            txn_by_date.setdefault(t["date"], []).append(_to_decimal(t["amount"]))

        # Also get transactions before calc_start if we're restarting from the beginning
        if calc_start == start_date:
            pre_txns = db.execute(
                "SELECT date, amount FROM transactions WHERE loan_id = ? AND date < ? ORDER BY date, id",
                (loan_id, calc_start.isoformat()),
            ).fetchall()
            for t in pre_txns:
                txn_by_date.setdefault(t["date"], []).append(_to_decimal(t["amount"]))

        # Get all rate history
        rates = db.execute(
            "SELECT effective_date, prime_rate FROM rate_history ORDER BY effective_date"
        ).fetchall()
        rate_list = [(r["effective_date"], _to_decimal(r["prime_rate"])) for r in rates]

        spread = _to_decimal(loan["spread"])
        today = date.today()
        current_day = calc_start
        monthly_interest = Decimal("0")

        # If recomputing from the middle, we need to recover the accumulated monthly interest
        if calc_start > start_date and calc_start.day > 1:
            # Sum interest from beginning of this month to calc_start
            month_start = calc_start.replace(day=1)
            interest_rows = db.execute(
                "SELECT SUM(interest_accrued) as total FROM daily_balances WHERE loan_id = ? AND date >= ? AND date < ?",
                (loan_id, month_start.isoformat(), calc_start.isoformat()),
            ).fetchone()
            if interest_rows and interest_rows["total"]:
                monthly_interest = _to_decimal(interest_rows["total"])

        while current_day <= today:
            day_str = current_day.isoformat()
            opening_balance = current_balance

            # Apply transactions for this day
            if day_str in txn_by_date:
                for amt in txn_by_date[day_str]:
                    current_balance += amt  # negative = payment, positive = disbursement

            # Get effective rate for this day
            prime = _get_rate_for_date(rate_list, day_str)
            if prime is None:
                # No rate available, skip interest
                effective_rate = spread
            else:
                effective_rate = prime + spread

            # Calculate daily interest
            if current_balance > 0:
                daily_interest = (
                    current_balance * effective_rate / Decimal("100") / Decimal("365")
                )
                daily_interest = daily_interest.quantize(
                    Decimal("0.0000001"), rounding=ROUND_HALF_UP
                )
            else:
                daily_interest = Decimal("0")

            monthly_interest += daily_interest

            # Check if last day of month → compound
            last_day = calendar.monthrange(current_day.year, current_day.month)[1]
            if current_day.day == last_day:
                current_balance += monthly_interest.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                monthly_interest = Decimal("0")

            closing_balance = current_balance

            db.execute(
                """INSERT OR REPLACE INTO daily_balances
                   (loan_id, date, opening_balance, interest_accrued, closing_balance, effective_rate)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    loan_id,
                    day_str,
                    float(opening_balance),
                    float(daily_interest),
                    float(closing_balance),
                    float(effective_rate),
                ),
            )

            current_day += timedelta(days=1)

        db.commit()
    finally:
        db.close()


def _get_rate_for_date(rate_list: list[tuple[str, Decimal]], day_str: str) -> Decimal | None:
    """Binary-ish search for effective rate on a given date."""
    result = None
    for eff_date, rate in rate_list:
        if eff_date <= day_str:
            result = rate
        else:
            break
    return result


def get_current_balance(loan_id: int) -> dict | None:
    """Get the most recent balance info for a loan."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM daily_balances WHERE loan_id = ? ORDER BY date DESC LIMIT 1",
            (loan_id,),
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        db.close()
