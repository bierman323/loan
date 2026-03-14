from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.services.rate_fetcher import fetch_and_store_rate
from backend.services.interest_engine import recompute_daily_balances
from backend.database import get_db


scheduler = AsyncIOScheduler()


async def daily_job():
    """Fetch rate and recompute balances for all loans."""
    await fetch_and_store_rate()

    db = get_db()
    try:
        loans = db.execute("SELECT id FROM loans").fetchall()
    finally:
        db.close()

    for loan in loans:
        recompute_daily_balances(loan["id"])


def start_scheduler():
    scheduler.add_job(daily_job, CronTrigger(hour=0, minute=5), id="daily_rate_and_interest")
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
