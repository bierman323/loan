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
- **Rate source**: Bank of Canada Valet API at `https://www.bankofcanada.ca/valet/observations/V80691311/json?recent=1`. Fetched daily by APScheduler. Fallback to most recent rate in `rate_history` table.
- **Payment/term duality**: user can provide either payment or term; the backend calculates the other via `_resolve_payment_and_term()`. When adjusting mid-loan, recalculation uses *current balance*, not initial amount.
- **Schema migrations** are manual `ALTER TABLE` statements in `init_db()` in `database.py`. Check existing columns with `PRAGMA table_info` before altering.

## Running locally

```bash
# Backend
pip3 install -r backend/requirements.txt
DATABASE_PATH=./data/loan_tracker.db python3 -m uvicorn backend.main:app --port 8080

# Frontend dev
cd frontend && npm install && npm run dev

# Frontend prod build
cd frontend && npm run build && cp -r dist ../static
```

## Running with Docker

```bash
docker compose up --build
# App at http://localhost:8080, data in ./data/
```

## Common tasks

### Add a new database column
1. Add to `SCHEMA` in `database.py`
2. Add migration in `init_db()` with `ALTER TABLE`
3. Add to Pydantic models in `models.py`
4. Add to TypeScript types in `frontend/src/types/index.ts`
5. Wire into routers and components

### Rebuild after frontend changes
```bash
cd frontend && npm run build
rm -rf static && cp -r frontend/dist static
# Restart uvicorn
```

## File layout

- `backend/services/interest_engine.py` — daily interest calculation, balance recomputation
- `backend/services/projection_engine.py` — what-if payoff simulator
- `backend/services/rate_fetcher.py` — Bank of Canada API + fallback
- `backend/routers/loans.py` — CRUD + `_enrich_loan()` adds computed fields (interest paid, interest remaining)
- `frontend/src/components/Dashboard.tsx` — editable payment/term/frequency cards + metrics
- `frontend/src/api/client.ts` — axios with token interceptor

## Things to be careful about

- The `daily_balances` table is a computed cache. Never edit it directly — always go through `recompute_daily_balances()`.
- Transaction amounts: **negative = payment**, **positive = disbursement**. The initial loan amount is a positive transaction.
- The projection engine simulates day-by-day. Payment intervals must match frequency: weekly=7 days, biweekly=14 days, monthly=30 days.
- When changing `effective_rate` comparisons or lookups, remember that `daily_balances.effective_rate` stores the full rate (prime + spread), not just the spread.
