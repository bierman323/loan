from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from datetime import date, timedelta
import calendar
from backend.database import get_db
from backend.services.interest_engine import _to_decimal
from backend.services.rate_fetcher import get_latest_rate


MAX_PROJECTION_YEARS = 30

# A regular payment that would leave less than this fraction of a payment owing pays the
# loan off instead (the final payment absorbs the remainder, as lenders do). Without this,
# the r/12 amortization formula vs. daily accrual leaves a few dollars needing one more payment.
FINAL_PAYMENT_TOLERANCE = Decimal("0.02")


# --- Date helpers ---

def add_months(start: date, months: int) -> date:
    """Same day-of-month `months` later, clamped to the end of shorter months."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))


def nth_payment_date(anchor: date, frequency: str, n: int) -> date:
    """The n-th payment after anchor: weekly = 7 days, biweekly = 14 days, monthly = same day each month."""
    if frequency == "weekly":
        return anchor + timedelta(days=7 * n)
    if frequency == "monthly":
        return add_months(anchor, n)
    return anchor + timedelta(days=14 * n)


def first_date_after(anchor: date, frequency: str, after: date) -> date:
    """First scheduled date strictly after `after`, counting from anchor (anchor itself excluded)."""
    n = 1
    candidate = nth_payment_date(anchor, frequency, n)
    while candidate <= after:
        n += 1
        candidate = nth_payment_date(anchor, frequency, n)
    return candidate


# --- Loan state ---

@dataclass
class LoanSnapshot:
    """A loan's state at the end of today, taken from the daily_balances cache."""
    balance: Decimal
    annual_rate: Decimal  # prime + spread, in percent
    # Interest accrued since the last month-end that has not been compounded yet
    accrued_this_month: Decimal
    today: date


@dataclass
class LoanSchedule:
    """What the loan is expected to do from tomorrow on."""
    regular_payment: Decimal
    frequency: str
    first_payment_date: date
    draw_amount: Decimal = Decimal("0")
    draw_dates: list[date] = field(default_factory=list)
    repayment_start_date: date | None = None


@dataclass
class SimulationResult:
    trajectory: list[dict]
    pays_off: bool

    @property
    def payoff_date(self) -> date | None:
        if self.pays_off and self.trajectory:
            return self.trajectory[-1]["date"]
        return None

    @property
    def total_interest(self) -> Decimal:
        return sum((p["interest"] for p in self.trajectory), Decimal("0"))

    def balance_on(self, target: date) -> Decimal | None:
        for point in self.trajectory:
            if point["date"] == target:
                return point["balance"]
        return None

    def owed_on(self, target: date) -> Decimal | None:
        """Balance plus interest accrued this month but not yet compounded."""
        for point in self.trajectory:
            if point["date"] == target:
                return point["balance"] + point["accrued"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return None


def get_snapshot(db, loan) -> LoanSnapshot:
    today = date.today()
    bal_row = db.execute(
        "SELECT date, closing_balance, effective_rate FROM daily_balances WHERE loan_id = ? ORDER BY date DESC LIMIT 1",
        (loan["id"],),
    ).fetchone()

    if bal_row:
        balance = _to_decimal(bal_row["closing_balance"])
        annual_rate = _to_decimal(bal_row["effective_rate"])
        # Carry this month's uncompounded interest forward so it is compounded at month-end
        # in the simulation. If the cached day is a month-end it was already compounded.
        cached_day = date.fromisoformat(bal_row["date"])
        is_month_end = cached_day.day == calendar.monthrange(cached_day.year, cached_day.month)[1]
        accrued_this_month = Decimal("0")
        if not is_month_end:
            row = db.execute(
                "SELECT COALESCE(SUM(interest_accrued), 0) AS total FROM daily_balances WHERE loan_id = ? AND date >= ? AND date <= ?",
                (loan["id"], cached_day.replace(day=1).isoformat(), cached_day.isoformat()),
            ).fetchone()
            accrued_this_month = _to_decimal(row["total"])
    else:
        # Loan starts in the future: nothing has been computed yet
        balance = _to_decimal(loan["initial_amount"])
        prime = get_latest_rate() or 0
        annual_rate = _to_decimal(prime) + _to_decimal(loan["spread"])
        accrued_this_month = Decimal("0")

    return LoanSnapshot(balance=balance, annual_rate=annual_rate, accrued_this_month=accrued_this_month, today=today)


def get_schedule(db, loan, today: date) -> LoanSchedule:
    frequency = loan["payment_frequency"]
    start_date = date.fromisoformat(loan["start_date"])
    repayment_start = date.fromisoformat(loan["repayment_start_date"]) if loan["repayment_start_date"] else None

    # Payments are counted from when repayment begins (or the loan start), or from the
    # most recent payment if one was made after that.
    payment_anchor = repayment_start or start_date
    last_payment = db.execute(
        "SELECT MAX(date) AS d FROM transactions WHERE loan_id = ? AND amount < 0 AND date <= ?",
        (loan["id"], today.isoformat()),
    ).fetchone()["d"]
    if last_payment and date.fromisoformat(last_payment) >= payment_anchor:
        payment_anchor = date.fromisoformat(last_payment)
    first_payment_date = first_date_after(payment_anchor, frequency, max(today, payment_anchor))

    # Planned monthly draws continue one month after the most recent draw of the planned
    # amount (so they fall on the same day as the regular draws), or after the loan start
    # if none has been recorded yet. Draws of other amounts are one-offs and do not shift
    # the schedule.
    draw_amount = _to_decimal(loan["planned_draw_amount"] or 0)
    draw_dates: list[date] = []
    if draw_amount > 0 and loan["planned_draw_end_date"]:
        draw_end = date.fromisoformat(loan["planned_draw_end_date"])
        last_regular_draw = db.execute(
            "SELECT MAX(date) AS d FROM transactions WHERE loan_id = ? AND amount = ? AND date <= ?",
            (loan["id"], float(draw_amount), today.isoformat()),
        ).fetchone()["d"]
        draw_anchor = date.fromisoformat(last_regular_draw) if last_regular_draw else start_date
        n = 1
        next_draw = add_months(draw_anchor, n)
        while next_draw <= draw_end:
            if next_draw > today:
                draw_dates.append(next_draw)
            n += 1
            next_draw = add_months(draw_anchor, n)

    return LoanSchedule(
        regular_payment=_to_decimal(loan["regular_payment"]),
        frequency=frequency,
        first_payment_date=first_payment_date,
        draw_amount=draw_amount,
        draw_dates=draw_dates,
        repayment_start_date=repayment_start,
    )


# --- Simulation ---

def simulate(
    snapshot: LoanSnapshot,
    schedule: LoanSchedule,
    extra_onetime: Decimal = Decimal("0"),
    extra_date: date | None = None,
    extra_recurring: Decimal = Decimal("0"),
    stop_after: date | None = None,
    include_payments: bool = True,
    final_payment_tolerance: Decimal = FINAL_PAYMENT_TOLERANCE,
) -> SimulationResult:
    """
    Simulate the loan day by day from tomorrow, using the same interest model as the
    interest engine: daily accrual on the balance after that day's transactions,
    compounded into the balance on the last day of each month.

    Each day: planned draw, then extra one-time payment, then regular payment, then interest.
    The trajectory's "interest" is each day's accrual, so its sum is the future interest
    only (interest accrued up to today is already in daily_balances).
    """
    balance = snapshot.balance
    rate = snapshot.annual_rate
    monthly_interest = snapshot.accrued_this_month
    cum_interest = Decimal("0")
    trajectory: list[dict] = []

    draw_set = set(schedule.draw_dates)
    last_draw_date = max(schedule.draw_dates) if schedule.draw_dates else None
    payment_total = schedule.regular_payment + extra_recurring
    payments_active = include_payments and payment_total > 0

    day = snapshot.today + timedelta(days=1)
    if extra_date is None or extra_date < day:
        extra_date = day

    # How far to look ahead
    horizon_start = max(d for d in [snapshot.today, schedule.repayment_start_date, last_draw_date] if d is not None)
    if stop_after is not None:
        end_date = stop_after
    elif payments_active:
        end_date = horizon_start + timedelta(days=MAX_PROJECTION_YEARS * 365)
    else:
        # Without payments the balance never falls; show it through the borrowing period only
        end_date = horizon_start

    if balance <= 0 and not draw_set:
        return SimulationResult(trajectory=[], pays_off=True)

    payment_number = 0
    next_payment = schedule.first_payment_date

    while day <= end_date:
        if day in draw_set:
            balance += schedule.draw_amount

        if day == extra_date and extra_onetime > 0:
            balance -= min(extra_onetime, balance)

        if payments_active and day == next_payment:
            remainder_after_payment = balance - payment_total
            if remainder_after_payment < payment_total * final_payment_tolerance:
                balance = Decimal("0")  # final payment
            else:
                balance = remainder_after_payment
            payment_number += 1
            next_payment = nth_payment_date(schedule.first_payment_date, schedule.frequency, payment_number)

        if balance > 0:
            daily_interest = (balance * rate / Decimal("100") / Decimal("365")).quantize(
                Decimal("0.0000001"), rounding=ROUND_HALF_UP
            )
        else:
            daily_interest = Decimal("0")
        monthly_interest += daily_interest
        cum_interest += daily_interest

        is_month_end = day.day == calendar.monthrange(day.year, day.month)[1]
        if is_month_end:
            balance += monthly_interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            monthly_interest = Decimal("0")

        trajectory.append({
            "date": day,
            "balance": balance,
            # Interest accrued this month but not yet compounded: owed, just not in the balance yet
            "accrued": monthly_interest,
            "interest": daily_interest,
            "cum_interest": cum_interest,
        })

        no_more_draws = last_draw_date is None or day >= last_draw_date
        if balance <= 0 and no_more_draws:
            return SimulationResult(trajectory=trajectory, pays_off=True)

        day += timedelta(days=1)

    return SimulationResult(trajectory=trajectory, pays_off=False)


# --- Public API ---

def projected_balance_at(loan_id: int, target: date) -> float | None:
    """
    Projected balance at the end of `target`, including planned draws and compounding
    but no regular payments. Used to size the payment for when repayment begins.
    """
    db = get_db()
    try:
        loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not loan:
            return None
        snapshot = get_snapshot(db, loan)
        if target <= snapshot.today:
            return float(snapshot.balance)
        schedule = get_schedule(db, loan, snapshot.today)
        result = simulate(snapshot, schedule, stop_after=target, include_payments=False)
        if not result.trajectory:
            return float(snapshot.balance)
        return float(result.owed_on(target))
    finally:
        db.close()


def exact_payment_for_term(loan_id: int, term_months: int, payments_per_year: int, guess: float) -> float | None:
    """
    The level payment that leaves exactly nothing owing after the last payment of the
    term, under the same simulation used for projections (daily accrual, month-end
    compounding, planned draws, real calendar). The textbook r/12 formula is close but
    leaves a few dollars over, which would need one more payment.

    What is owed after the last payment is linear in the payment amount, so evaluating
    two payments that are both too small gives the exact answer in one secant step.
    Returns None if it cannot be calculated (e.g. no payment dates in range).
    """
    db = get_db()
    try:
        loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not loan or guess <= 0:
            return None
        snapshot = get_snapshot(db, loan)
        schedule = get_schedule(db, loan, snapshot.today)
    finally:
        db.close()

    number_of_payments = round(term_months * payments_per_year / 12)
    if number_of_payments < 1:
        return None
    last_payment_date = nth_payment_date(schedule.first_payment_date, schedule.frequency, number_of_payments - 1)

    def owed_after_last_payment(payment: Decimal) -> Decimal | None:
        schedule.regular_payment = payment
        result = simulate(snapshot, schedule, stop_after=last_payment_date, final_payment_tolerance=Decimal("0"))
        return result.owed_on(last_payment_date)

    low = _to_decimal(guess) * Decimal("0.90")
    high = _to_decimal(guess) * Decimal("0.95")
    owed_low = owed_after_last_payment(low)
    owed_high = owed_after_last_payment(high)
    if owed_low is None or owed_high is None or owed_low == owed_high:
        return None
    exact = high - owed_high * (high - low) / (owed_high - owed_low)
    # Round up to the cent so the last payment clears the balance
    return float(exact.quantize(Decimal("0.01"), rounding=ROUND_CEILING))


def project_payoff(
    loan_id: int,
    extra_payment: float = 0,
    extra_payment_date: date | None = None,
    extra_recurring: float = 0,
) -> dict:
    """
    Project two trajectories:
    1. Current: regular payments and planned draws
    2. Modified: with extra one-time and/or recurring payments
    """
    db = get_db()
    try:
        loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
        if not loan:
            return {}
        snapshot = get_snapshot(db, loan)
        schedule = get_schedule(db, loan, snapshot.today)
    finally:
        db.close()

    current = simulate(snapshot, schedule)
    new = simulate(
        snapshot, schedule,
        extra_onetime=_to_decimal(extra_payment),
        extra_date=extra_payment_date,
        extra_recurring=_to_decimal(extra_recurring),
    )

    # Savings only mean something when the current plan actually ends
    interest_saved = None
    months_saved = None
    if current.pays_off and new.pays_off:
        interest_saved = float(current.total_interest - new.total_interest)
        months_saved = _months_diff(current.payoff_date, new.payoff_date)

    balance_at_repayment_start = None
    if schedule.repayment_start_date and schedule.repayment_start_date > snapshot.today:
        balance = current.owed_on(schedule.repayment_start_date)
        if balance is not None:
            balance_at_repayment_start = float(balance)

    return {
        "current_payoff_date": current.payoff_date,
        "current_pays_off": current.pays_off,
        "current_total_interest": float(current.total_interest),
        "new_payoff_date": new.payoff_date,
        "new_pays_off": new.pays_off,
        "new_total_interest": float(new.total_interest),
        "interest_saved": interest_saved,
        "months_saved": months_saved,
        "balance_at_repayment_start": balance_at_repayment_start,
        "current_trajectory": _sample_trajectory(current.trajectory),
        "new_trajectory": _sample_trajectory(new.trajectory),
    }


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


def _months_diff(d1: date, d2: date) -> float:
    return round((d1 - d2).days / 30.44, 1)
