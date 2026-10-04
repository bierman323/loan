# Loan Tracker — Claude Code Context

## What this project is

A web app for tracking personal loans with CIBC PLC-style interest (daily accrual, monthly compounding at prime + spread). Built for a father tracking loans to family members.

## Stack

- **Backend**: Python 3.12 / FastAPI / SQLite (WAL mode)
- **Frontend**: React 18 / TypeScript / Vite / Tailwind CSS / Recharts
- **Deployment**: Docker (multi-stage build), single container, SQLite volume-mounted to `./data/`

## Key architectural decisions

- **Interest engine** (`backend/services/interest_engine.py`) is the critical path. It uses Python `Decimal` for precision. All balance changes trigger `recompute_daily_balances()` from the affected date forward.
- **No authentication** — users are identified by a UUID token in `localStorage` and `X-User-Token` header. Privacy, not security.
- **Loans start at balance 0** — the initial amount is recorded as a positive transaction (disbursement). Do NOT also start the balance at `initial_amount` or it will be double-counted.
- **Rate source**: Bank of Canada Valet API, series `V80691311` (weekly, Wednesdays). `sync_rate_history()` stores the observation date (not the fetch date), only inserts a row when the rate changes, and backfills to the earliest loan start. Runs at startup and daily at 00:05, followed by a full recompute of all loans. Days before the first stored rate use the earliest known rate.
- **Payment/term duality**: user can provide either payment or term; the backend calculates the other via `_resolve_payment_and_term()` (math in `services/loan_plan.py`). When adjusting mid-loan, recalculation uses *current balance*, not initial amount — or, during a borrowing phase, the *projected balance at repayment start*.
- **Borrowing phase (draws over time)**: `planned_draw_amount` / `planned_draw_end_date` describe planned monthly draws (projection only — actual draws are recorded as positive transactions). Planned draws repeat on the loan start's day of month. No payments are due before `repayment_start_date`; the first payment is one period after it. While in the borrowing phase, `regular_payment` is an estimate re-sized from `term_months` by `refresh_estimated_payment()` after anything that changes the projected balance (transactions, rates, plan edits, daily job).
- **`planned_maturity_date`** is the payoff baseline for the Term Shift card. `term_months` gets overwritten with the remaining term when the payment is adjusted, so never derive the baseline from it. Only explicit term changes (or any re-plan before repayment begins) move `planned_maturity_date`.
- **Static serving** in `main.py` resolves paths and refuses anything outside `static/` (path traversal once exposed the SQLite DB). Unknown `/api/*` paths return 404.
- **Schema migrations** are manual `ALTER TABLE` statements in `init_db()` in `database.py`. Check existing columns with `PRAGMA table_info` before altering.

## Running locally

```bash
# Backend
pip3 install -r backend/requirements.txt
DATABASE_PATH=./data/loan_tracker.db python3 -m uvicorn backend.main:app --port 8080

# Frontend dev
cd frontend && npm install && npm run dev

# Frontend prod build (replaces ./static)
cd frontend && npm run build:static

# Tests
pip3 install -r backend/requirements-dev.txt
python3 -m pytest backend/tests
```

## Running with Docker

```bash
docker compose up --build
# App at http://localhost:8086 (host port in docker-compose.yml), data in ./data/
```

## Common tasks

### Add a new database column
1. Add to `SCHEMA` in `database.py`
2. Add migration in `init_db()` with `ALTER TABLE` (backfill existing rows if needed)
3. Add to Pydantic models in `models.py`
4. Add to TypeScript types in `frontend/src/types/index.ts`
5. Wire into routers and components

### Rebuild after frontend changes
```bash
cd frontend && npm run build:static
# Restart uvicorn
```

## File layout

- `backend/services/interest_engine.py` — daily interest calculation, balance recomputation
- `backend/services/projection_engine.py` — day-by-day payoff simulator (planned draws, payment schedule, what-if)
- `backend/services/loan_plan.py` — payment/term math, borrowing-phase payment estimate
- `backend/tests/` — pytest suite (each test gets a temp DB)
- `backend/services/rate_fetcher.py` — Bank of Canada API + fallback
- `backend/routers/loans.py` — CRUD + `_enrich_loan()` adds computed fields (interest paid, interest remaining)
- `frontend/src/components/Dashboard.tsx` — editable payment/term/frequency cards + metrics
- `frontend/src/api/client.ts` — axios with token interceptor

## Things to be careful about

- The `daily_balances` table is a computed cache. Never edit it directly — always go through `recompute_daily_balances()`.
- Transaction amounts: **negative = payment**, **positive = disbursement**. The initial loan amount is a positive transaction.
- The projection engine simulates day-by-day from tomorrow, carrying this month's uncompounded interest forward. Payment intervals: weekly=7 days, biweekly=14 days, monthly=same day each calendar month (see `nth_payment_date()`). The next payment is scheduled from the last recorded payment.
- Transactions cannot be dated before the loan start (balances are only computed from the start).
- When changing `effective_rate` comparisons or lookups, remember that `daily_balances.effective_rate` stores the full rate (prime + spread), not just the spread.
