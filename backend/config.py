import os

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/loan_tracker.db")
DEFAULT_SPREAD = 0.5  # percentage above prime; the single source for new-loan defaults
DEFAULT_PAYMENT_FREQUENCY = "biweekly"
BANK_OF_CANADA_SERIES_ID = "V80691311"  # Prime rate (weekly, Wednesdays)
BANK_OF_CANADA_SERIES_URL = (
    f"https://www.bankofcanada.ca/valet/observations/{BANK_OF_CANADA_SERIES_ID}/json"
)
