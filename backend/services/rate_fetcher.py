import httpx
from datetime import date, datetime, timedelta
from backend.config import BANK_OF_CANADA_SERIES_URL, BANK_OF_CANADA_SERIES_ID
from backend.database import get_db


async def fetch_prime_rate_observations(start_date: date) -> list[tuple[date, float]] | None:
    """
    Fetch prime rate observations from the Bank of Canada Valet API from start_date to today.

    The series is published weekly (Wednesdays). Returns (observation_date, rate) pairs in
    date order, or None if the API could not be reached.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                BANK_OF_CANADA_SERIES_URL,
                params={"start_date": start_date.isoformat()},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"Failed to fetch rate from Bank of Canada: {e}")
        return None

    observations = []
    for obs in data.get("observations", []):
        rate_str = obs.get(BANK_OF_CANADA_SERIES_ID, {}).get("v")
        obs_date_str = obs.get("d")
        if rate_str and obs_date_str:
            observations.append((date.fromisoformat(obs_date_str), float(rate_str)))
    observations.sort()
    return observations


def get_latest_rate() -> float | None:
    """Get the most recent prime rate from the database."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT prime_rate FROM rate_history ORDER BY effective_date DESC, id DESC LIMIT 1"
        ).fetchone()
        return row["prime_rate"] if row else None
    finally:
        db.close()


def get_rate_for_date(target_date: date) -> float | None:
    """Get the effective prime rate for a given date."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT prime_rate FROM rate_history WHERE effective_date <= ? ORDER BY effective_date DESC, id DESC LIMIT 1",
            (target_date.isoformat(),),
        ).fetchone()
        return row["prime_rate"] if row else None
    finally:
        db.close()


def get_earliest_rate_date() -> date | None:
    db = get_db()
    try:
        row = db.execute("SELECT MIN(effective_date) AS earliest FROM rate_history").fetchone()
        return date.fromisoformat(row["earliest"]) if row and row["earliest"] else None
    finally:
        db.close()


async def sync_rate_history(start_date: date) -> date | None:
    """
    Make sure rate_history covers start_date through today using Bank of Canada data.

    A row is only inserted when the observed rate differs from the rate already in effect
    on that date, so unchanged weeks do not create duplicate rows. Because the series is
    weekly, a mid-week rate change is recorded on the following Wednesday's observation;
    use a manual override for exact change dates.

    Returns the earliest effective_date that was inserted (so callers can recompute
    balances from there), or None if nothing changed.
    """
    # Start two weeks earlier so there is an observation on or before start_date
    observations = await fetch_prime_rate_observations(start_date - timedelta(days=14))

    earliest_inserted: date | None = None
    db = get_db()
    try:
        for obs_date, rate in observations or []:
            in_effect = db.execute(
                "SELECT prime_rate FROM rate_history WHERE effective_date <= ? ORDER BY effective_date DESC, id DESC LIMIT 1",
                (obs_date.isoformat(),),
            ).fetchone()
            if in_effect is not None and in_effect["prime_rate"] == rate:
                continue
            db.execute(
                "INSERT INTO rate_history (effective_date, prime_rate, source, fetched_at) VALUES (?, ?, 'bank_of_canada_api', ?)",
                (obs_date.isoformat(), rate, datetime.now().isoformat()),
            )
            if earliest_inserted is None or obs_date < earliest_inserted:
                earliest_inserted = obs_date

        remove_redundant_api_rates(db)
        db.commit()
    finally:
        db.close()
    return earliest_inserted


def remove_redundant_api_rates(db) -> None:
    """
    Delete Bank of Canada rows that repeat the rate already in effect before them.

    These rows never change any calculation; they only clutter the rate history.
    Manual rows are always kept.
    """
    rows = db.execute(
        "SELECT id, prime_rate, source FROM rate_history ORDER BY effective_date, id"
    ).fetchall()
    previous_rate = None
    for row in rows:
        is_repeat = previous_rate is not None and row["prime_rate"] == previous_rate
        if is_repeat and row["source"] == "bank_of_canada_api":
            db.execute("DELETE FROM rate_history WHERE id = ?", (row["id"],))
            continue
        previous_rate = row["prime_rate"]
