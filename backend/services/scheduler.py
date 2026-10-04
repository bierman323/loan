from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.services.rate_fetcher import sync_rate_history
from backend.services.interest_engine import recompute_daily_balances
from backend.services.loan_plan import refresh_all_estimated_payments
from backend.database import get_db


scheduler = AsyncIOScheduler()


async def daily_job():
    """Sync prime rates (back to the earliest loan start) and recompute balances for all loans."""
    db = get_db()
    try:
        loans = db.execute("SELECT id, start_date FROM loans").fetchall()
    finally:
        db.close()

    # Always look back at least 30 days so a missed week of fetches is caught up
    sync_from = date.today() - timedelta(days=30)
    for loan in loans:
        loan_start = date.fromisoformat(loan["start_date"])
        if loan_start < sync_from:
            sync_from = loan_start
    await sync_rate_history(sync_from)

    for loan in loans:
        recompute_daily_balances(loan["id"])

    # Borrowing-phase payments follow the projected balance, which moves daily with interest
    refresh_all_estimated_payments()


def start_scheduler():
    scheduler.add_job(daily_job, CronTrigger(hour=0, minute=5), id="daily_rate_and_interest")
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
