from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
import calendar
from backend.database import get_db
from backend.services.interest_engine import _to_decimal
from backend.services.rate_fetcher import get_latest_rate


def project_payoff(
    loan_id: int,
    extra_payment: float = 0,
    extra_payment_date: date | None = None,
    extra_recurring: float = 0,
) -> dict:
    """
    Project two trajectories:
    1. Current: regular payments only
    2. Modified: with extra one-time and/or recurring payments
    """
    db = get_db()
    try:
        loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not loan:
            return {}

        # Get current balance and rate
        bal_row = db.execute(
            "SELECT closing_balance, effective_rate FROM daily_balances WHERE loan_id = ? ORDER BY date DESC LIMIT 1",
            (loan_id,),
        ).fetchone()

        if bal_row:
            starting_balance = _to_decimal(bal_row["closing_balance"])
            effective_rate = _to_decimal(bal_row["effective_rate"])
        else:
            starting_balance = _to_decimal(loan["initial_amount"])
            # Use actual prime + spread, not just spread
            prime = get_latest_rate() or Decimal("0")
            effective_rate = _to_decimal(prime) + _to_decimal(loan["spread"])

        regular_payment = _to_decimal(loan["regular_payment"])
        frequency = loan["payment_frequency"]
        term_months = loan["term_months"]

        if extra_payment_date is None:
            extra_payment_date = date.today()

        # Calculate both trajectories
        current_traj = _simulate(
            starting_balance, effective_rate, regular_payment, frequency,
            Decimal("0"), None, Decimal("0"), term_months,
        )
        new_traj = _simulate(
            starting_balance, effective_rate, regular_payment, frequency,
            _to_decimal(extra_payment), extra_payment_date, _to_decimal(extra_recurring),
            term_months,
        )

        current_interest = sum(p["interest"] for p in current_traj)
        new_interest = sum(p["interest"] for p in new_traj)

        return {
            "current_payoff_date": current_traj[-1]["date"] if current_traj else None,
            "current_total_interest": float(current_interest),
            "new_payoff_date": new_traj[-1]["date"] if new_traj else None,
            "new_total_interest": float(new_interest),
            "interest_saved": float(current_interest - new_interest),
            "months_saved": _months_diff(
                current_traj[-1]["date"] if current_traj else date.today(),
                new_traj[-1]["date"] if new_traj else date.today(),
            ),
            "current_trajectory": _sample_trajectory(current_traj),
            "new_trajectory": _sample_trajectory(new_traj),
        }
    finally:
        db.close()


def _sample_trajectory(traj: list[dict], max_points: int = 200) -> list[dict]:
    """Sample trajectory to reasonable number of chart points."""
    if not traj:
        return []
    step = max(1, len(traj) // max_points)
    sampled = traj[::step]
    # Always include the last point
    if sampled[-1] is not traj[-1]:
        sampled.append(traj[-1])
    return [
        {"date": p["date"], "balance": float(p["balance"]), "cumulative_interest": float(p["cum_interest"])}
        for p in sampled
    ]


def _payment_interval_days(frequency: str) -> int:
    return {"weekly": 7, "biweekly": 14, "monthly": 30}.get(frequency, 14)


def _simulate(
    balance: Decimal,
    annual_rate: Decimal,
    regular_payment: Decimal,
    frequency: str,
    extra_onetime: Decimal,
    extra_date: date | None,
    extra_recurring: Decimal,
    term_months: int | None = None,
    max_years: int = 30,
) -> list[dict]:
    """Simulate loan payoff day by day."""
    if balance <= 0 or regular_payment <= 0:
        return []

    today = date.today()
    current_day = today

    # Cap simulation at term if set, otherwise max_years
    if term_months:
        end_date = today + timedelta(days=int(term_months * 30.44) + 90)  # small buffer past term
    else:
        end_date = today + timedelta(days=max_years * 365)

    monthly_interest = Decimal("0")
    cum_interest = Decimal("0")
    trajectory = []

    interval_days = _payment_interval_days(frequency)
    next_payment = today + timedelta(days=interval_days)

    while current_day <= end_date and balance > 0:
        # Apply extra one-time payment
        if extra_date and current_day == extra_date and extra_onetime > 0:
            balance -= extra_onetime
            if balance <= 0:
                balance = Decimal("0")
                trajectory.append({
                    "date": current_day,
                    "balance": balance,
                    "interest": Decimal("0"),
                    "cum_interest": cum_interest,
                })
                break

        # Apply regular + extra recurring payments on payment dates
        if current_day == next_payment:
            total_payment = regular_payment + extra_recurring
            if total_payment > balance:
                total_payment = balance
            balance -= total_payment
            next_payment += timedelta(days=interval_days)

            if balance <= 0:
                balance = Decimal("0")
                trajectory.append({
                    "date": current_day,
                    "balance": balance,
                    "interest": Decimal("0"),
                    "cum_interest": cum_interest,
                })
                break

        # Daily interest
        if balance > 0:
            daily_interest = (
                balance * annual_rate / Decimal("100") / Decimal("365")
            ).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
            monthly_interest += daily_interest
        else:
            daily_interest = Decimal("0")

        # Monthly compounding
        last_day = calendar.monthrange(current_day.year, current_day.month)[1]
        if current_day.day == last_day:
            compound = monthly_interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            balance += compound
            cum_interest += compound
            monthly_interest = Decimal("0")

        trajectory.append({
            "date": current_day,
            "balance": balance,
            "interest": daily_interest,
            "cum_interest": cum_interest,
        })

        current_day += timedelta(days=1)

    return trajectory


def _months_diff(d1: date, d2: date) -> float:
    return round((d1 - d2).days / 30.44, 1)
