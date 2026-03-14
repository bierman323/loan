import httpx
from datetime import date, datetime
from backend.config import BANK_OF_CANADA_API_URL
from backend.database import get_db


async def fetch_prime_rate() -> float | None:
    """Fetch current prime rate from Bank of Canada Valet API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BANK_OF_CANADA_API_URL)
            resp.raise_for_status()
            data = resp.json()
            observations = data.get("observations", [])
            if observations:
                latest = observations[-1]
                rate_str = latest.get("V80691311", {}).get("v")
                if rate_str:
                    return float(rate_str)
    except Exception as e:
        print(f"Failed to fetch rate from Bank of Canada: {e}")
    return None


def get_latest_rate() -> float | None:
    """Get the most recent prime rate from the database."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT prime_rate FROM rate_history ORDER BY effective_date DESC LIMIT 1"
        ).fetchone()
        return row["prime_rate"] if row else None
    finally:
        db.close()


def get_rate_for_date(target_date: date) -> float | None:
    """Get the effective prime rate for a given date."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT prime_rate FROM rate_history WHERE effective_date <= ? ORDER BY effective_date DESC LIMIT 1",
            (target_date.isoformat(),),
        ).fetchone()
        return row["prime_rate"] if row else None
    finally:
        db.close()


async def fetch_and_store_rate() -> float | None:
    """Fetch rate from API and store if it's new."""
    rate = await fetch_prime_rate()
    if rate is None:
        return get_latest_rate()

    today = date.today()
    db = get_db()
    try:
        existing = db.execute(
            "SELECT prime_rate FROM rate_history WHERE effective_date = ? AND source = 'bank_of_canada_api'",
            (today.isoformat(),),
        ).fetchone()

        if not existing or existing["prime_rate"] != rate:
            db.execute(
                "INSERT INTO rate_history (effective_date, prime_rate, source, fetched_at) VALUES (?, ?, 'bank_of_canada_api', ?)",
                (today.isoformat(), rate, datetime.now().isoformat()),
            )
            db.commit()
        return rate
    finally:
        db.close()
