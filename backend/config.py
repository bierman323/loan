import os

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/loan_tracker.db")
DEFAULT_SPREAD = 0.9  # percentage above prime
DEFAULT_PAYMENT_FREQUENCY = "biweekly"
BANK_OF_CANADA_API_URL = (
    "https://www.bankofcanada.ca/valet/observations/V80691311/json?recent=1"
)
