# Loan Tracker — Technical Specification

This document describes the complete behavior of the Loan Tracker application. Use it as a reference for what the system does, how it calculates, and what edge cases it handles. It reflects the final built state of the application.

---

## 1. Overview

A web application for tracking personal loans that use daily interest accrual with monthly compounding (the CIBC Personal Line of Credit model). Multiple users can track multiple loans independently with no authentication — just name-based user switching with browser-stored tokens.

**Stack**: Python 3.12 (FastAPI) backend, React 18 (TypeScript/Vite/Tailwind) frontend, SQLite database, single Docker container.

---

## 2. User System

### 2.1 Identity Model

- Users are identified by a UUID token (hex string), generated at creation time.
- The token is stored in the browser's `localStorage` under key `loan_tracker_token`.
- Every API request includes the token as an `X-User-Token` HTTP header.
- There are no passwords, sessions, or authentication. This provides privacy between household members, not security.

### 2.2 User Behavior

| Action | Behavior |
|--------|----------|
| Create user | Name required. UUID token generated. Token saved to localStorage. |
| Switch user | Token swaps in localStorage. All loan data reloads for new user. |
| Sign out | Token removed from localStorage. Landing page shown. |
| No token | API returns loans where `user_id IS NULL` (legacy/anonymous loans). |
| Invalid token | No loans returned (user_id lookup fails, treated as no match). |
| Delete user | User record deleted. Loans are **not** cascade-deleted (orphaned). |

---

## 3. Loan Management

### 3.1 Creating a Loan

Required fields: `name`, `start_date`, `initial_amount`.
Optional fields: `regular_payment`, `term_months`, `payment_frequency` (default: biweekly), `spread` (default: 0.9%).

**Payment/Term auto-calculation on create:**

| Provided | Calculated | Formula |
|----------|------------|---------|
| `term_months` only | `regular_payment` | `P × r / (1 - (1+r)^-n)` where `r = annual_rate / periods_per_year`, `n = term × periods_per_year / 12` |
| `regular_payment` only | `term_months` | `n = -log(1 - P×r/pmt) / log(1+r)`, converted to months |
| Both provided | Neither recalculated | Stored as-is |
| Neither provided | Payment = 0, term = null | Loan tracks balance only, no projections |

Where `annual_rate = (current_prime + spread) / 100` and `periods_per_year` = 52 (weekly), 26 (biweekly), or 12 (monthly).

**On creation:**
1. Loan record inserted with `user_id` from token.
2. A positive transaction is created for `initial_amount` with description "Initial disbursement".
3. `recompute_daily_balances()` runs from `start_date` to today.
4. Response includes computed fields (balance, interest, rate).

### 3.2 Adjusting a Loan Mid-Term

Users can adjust payment, term, or frequency after the loan is created. The key behavior: **recalculation uses the current balance, not the initial amount**, preserving all existing payment history.

| Field Changed | Effect |
|---------------|--------|
| `regular_payment` | `term_months` recalculated from current balance |
| `term_months` | `regular_payment` recalculated from current balance |
| `payment_frequency` | Stored; no automatic recalculation of payment/term |
| `spread` | Stored; full balance recomputation from loan start |
| `name` | Stored; no side effects |

### 3.3 Deleting a Loan

Deletes in order: `daily_balances` → `transactions` → `loans` record. No foreign key cascade relied upon for daily_balances (explicit delete).

---

## 4. Interest Calculation Engine

This is the core of the application. File: `backend/services/interest_engine.py`.

### 4.1 Algorithm

```
Starting balance = 0 (transactions provide the initial amount)
monthly_interest_accumulator = 0

For each day from loan.start_date to today:
  1. RATE LOOKUP: Find the most recent rate_history entry where effective_date <= current_day.
     If none exists: effective_rate = spread (no prime component).
     Otherwise: effective_rate = prime_rate + spread.

  2. APPLY TRANSACTIONS: Sum all transaction amounts for this day.
     Balance += sum(amounts)  // negative = payment, positive = disbursement

  3. DAILY INTEREST: If balance > 0:
     daily_interest = balance × (effective_rate / 100) / 365
     Rounded to 7 decimal places (ROUND_HALF_UP).
     monthly_interest_accumulator += daily_interest

  4. MONTHLY COMPOUNDING: If current_day is the last day of its calendar month:
     compound = monthly_interest_accumulator rounded to 2 decimal places (ROUND_HALF_UP)
     balance += compound
     monthly_interest_accumulator = 0

  5. STORE: Write (loan_id, date, opening_balance, interest_accrued, closing_balance, effective_rate)
     to daily_balances table (INSERT OR REPLACE).
```

### 4.2 Recomputation

`recompute_daily_balances(loan_id, from_date=None)` can recompute from an arbitrary date forward:

- If `from_date` is after `start_date`: retrieves the previous day's `closing_balance` as the starting point.
- If mid-month: recovers the monthly interest accumulator by summing `interest_accrued` from existing records for the current month.
- Deletes all `daily_balances` from `from_date` forward before recalculating.

### 4.3 Triggers for Recomputation

| Event | Recompute From |
|-------|---------------|
| Loan created | `start_date` |
| Transaction added | Transaction `date` |
| Transaction edited | `min(old_date, new_date)` |
| Transaction deleted | Deleted transaction's `date` |
| Rate added | Rate's `effective_date` (all loans) |
| Rate deleted | Deleted rate's `effective_date` (all loans) |
| Spread changed | `start_date` (full recompute) |
| Daily scheduler | Today (all loans) |

### 4.4 Precision

- All calculations use Python `Decimal` type.
- Daily interest: 7 decimal places.
- Monthly compound: 2 decimal places.
- Stored in SQLite as REAL (float64) — sufficient for dollar amounts.

---

## 5. Rate Management

### 5.1 Automatic Fetching

- **Source**: Bank of Canada Valet API
- **URL**: `https://www.bankofcanada.ca/valet/observations/V80691311/json?recent=1`
- **Field**: `observations[-1]["V80691311"]["v"]` (string → float)
- **Schedule**: Daily at 00:05 via APScheduler
- **On startup**: Fetched immediately during FastAPI lifespan startup
- **Failure handling**: Falls back to most recent rate in `rate_history`. No error raised.
- **Deduplication**: Only inserts if rate differs from existing entry for today with source `bank_of_canada_api`.

### 5.2 Manual Override

Users can add rate entries with source `manual` via the UI. These are treated identically to API-sourced rates for interest calculation — the engine uses the most recent rate by `effective_date` regardless of source.

### 5.3 Rate Deletion

Deleting a rate triggers recomputation of **all loans** from the deleted rate's `effective_date` forward.

---

## 6. Projection Engine

File: `backend/services/projection_engine.py`. Simulates future payoff day-by-day.

### 6.1 Inputs

| Field | Default | Description |
|-------|---------|-------------|
| `loan_id` | required | Loan to project |
| `extra_payment` | 0 | One-time lump sum payment |
| `extra_payment_date` | today | When the lump sum is applied |
| `extra_recurring` | 0 | Amount added to each regular payment |

### 6.2 Simulation

Two trajectories are simulated from today's balance:

1. **Current**: Regular payments only at the loan's `payment_frequency`.
2. **Scenario**: Same regular payments + extra one-time and/or extra recurring.

Each simulation:
- Runs day-by-day from today.
- Applies payments every `interval_days` (7/14/30 for weekly/biweekly/monthly).
- Uses the same interest model as the engine (daily accrual, monthly compounding).
- Stops when balance reaches 0 or simulation exceeds term (+ 90-day buffer) or 30 years.
- Caps payments to remaining balance (no negative balances).
- Uses the effective rate from the most recent `daily_balances` entry, or calculates from prime + spread if no balance history exists.

### 6.3 Output

| Field | Description |
|-------|-------------|
| `current_payoff_date` | Date balance reaches 0 (current trajectory) |
| `current_total_interest` | Sum of all daily interest (current) |
| `new_payoff_date` | Date balance reaches 0 (scenario) |
| `new_total_interest` | Sum of all daily interest (scenario) |
| `interest_saved` | `current_total_interest - new_total_interest` |
| `months_saved` | `(current_payoff_date - new_payoff_date) / 30.44` |
| `current_trajectory` | List of `{date, balance, cumulative_interest}` sampled to ~200 points |
| `new_trajectory` | Same structure for scenario |

---

## 7. Computed Loan Fields

Every loan response is enriched with computed fields via `_enrich_loan()`:

| Field | Source | Calculation |
|-------|--------|-------------|
| `current_balance` | `daily_balances` | Most recent `closing_balance` |
| `daily_interest` | `daily_balances` | Most recent `interest_accrued` |
| `effective_rate` | `daily_balances` | Most recent `effective_rate` |
| `interest_paid` | `daily_balances` | `SUM(interest_accrued)` across all days |
| `interest_remaining` | Projection engine | `current_total_interest` from projection (projected interest from today to payoff) |

---

## 8. Transaction Rules

- **Payments**: Recorded as negative amounts (e.g., -500.00).
- **Disbursements**: Recorded as positive amounts (e.g., 25000.00 for initial loan).
- **Multiple per day**: All transactions on the same date are applied in insertion order (by `id`) before interest is calculated for that day.
- **Editing a transaction**: Triggers recomputation from `min(old_date, new_date)` to cover both the original and new positions.
- **Deleting a transaction**: Triggers recomputation from the deleted transaction's date forward.
- **The initial disbursement**: Automatically created when a loan is created. Amount = `initial_amount`. This is why the engine starts balance at 0, not `initial_amount`.

---

## 9. Database Schema

### Tables

```sql
users (id, name, token UNIQUE, created_at)
loans (id, name, start_date, initial_amount, regular_payment, payment_frequency, spread, term_months, user_id → users.id, created_at)
transactions (id, loan_id → loans.id CASCADE, date, amount, description, created_at)
rate_history (id, effective_date, prime_rate, source, fetched_at)
daily_balances (loan_id + date PK, opening_balance, interest_accrued, closing_balance, effective_rate)
```

### Indexes

- `transactions(loan_id, date)`
- `rate_history(effective_date)`
- `daily_balances(loan_id, date)`

### Migrations

On startup, `init_db()` checks for missing columns and adds them:
- `loans.term_months` (INTEGER, nullable)
- `loans.user_id` (INTEGER, FK to users.id, nullable)

This allows the app to upgrade existing databases without data loss.

### SQLite Configuration

- `PRAGMA journal_mode=WAL` — allows concurrent reads during writes (scheduler + API).
- `PRAGMA foreign_keys=ON` — enforces FK constraints.

---

## 10. API Endpoints

### Users

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/users` | — | `User[]` |
| POST | `/api/users` | `{ name }` | `User` (201) |
| GET | `/api/users/by-token/{token}` | — | `User` or 404 |
| DELETE | `/api/users/{id}` | — | 204 |

### Loans (filtered by `X-User-Token` header)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/loans` | — | `Loan[]` (with computed fields) |
| POST | `/api/loans` | `LoanCreate` | `Loan` (201) |
| GET | `/api/loans/{id}` | — | `Loan` (with computed fields) |
| PATCH | `/api/loans/{id}` | `LoanUpdate` | `Loan` |
| DELETE | `/api/loans/{id}` | — | 204 |
| GET | `/api/loans/{id}/balances` | — | `DailyBalance[]` |

### Transactions

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/transactions?loan_id=` | — | `Transaction[]` |
| POST | `/api/transactions` | `TransactionCreate` | `Transaction` (201) |
| PATCH | `/api/transactions/{id}` | `TransactionUpdate` | `Transaction` |
| DELETE | `/api/transactions/{id}` | — | 204 |

### Rates

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/rates` | — | `Rate[]` |
| POST | `/api/rates` | `RateCreate` | `Rate` (201) |
| DELETE | `/api/rates/{id}` | — | 204 |

### Projections

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/projections` | `ProjectionRequest` | `ProjectionResponse` |

---

## 11. Frontend Components

| Component | Responsibility |
|-----------|---------------|
| `App` | Root state: current user, loan list, active loan, transactions, balances. Orchestrates data loading. |
| `UserSwitcher` | Dropdown in header. Create/switch/sign out. Manages localStorage token. |
| `LoanTabs` | Tab bar for loans. Create form with payment/term/frequency/spread. Double-click to rename. Delete with confirmation. |
| `Dashboard` | Top row: editable Payment, Frequency, Term cards (hover → "Adjust" button). Bottom row: Current Balance, Interest Paid, Interest Remaining, Effective Rate, Daily Interest, Principal Paid. |
| `PaymentForm` | Date (default: today), Amount (placeholder: regular payment; blank = use regular payment), Description. Submits negative transaction. |
| `PaymentHistory` | Sortable table (date, amount, description). Green for payments, red for disbursements. Delete with confirmation. |
| `BalanceChart` | Recharts `LineChart` of `closing_balance` over time. Sampled to 200 points max. |
| `ScenarioCalc` | One-time extra payment + recurring extra per payment. Shows interest saved, months saved, new payoff date. Dual-line comparison chart. |
| `RateHistory` | Rate table with source indicator. Manual override form. Delete with confirmation. |
| `Tooltip` | Reusable hover tooltip with arrow. |

---

## 12. Deployment

### Docker

Multi-stage Dockerfile:
1. `node:20-alpine` — `npm ci && npm run build` → produces `dist/`
2. `python:3.12-slim` — installs pip requirements, copies backend + frontend build, runs uvicorn

### docker-compose.yml

```yaml
services:
  loan-tracker:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_PATH=/app/data/loan_tracker.db
    restart: unless-stopped
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `data/loan_tracker.db` | SQLite database file path |

### Startup Sequence

1. `init_db()` — create tables, run migrations
2. `fetch_and_store_rate()` — fetch current prime rate from Bank of Canada
3. `start_scheduler()` — start daily rate fetch + balance recomputation job
4. Uvicorn begins serving on port 8080

### Static File Serving

- `/assets/*` mounted as static files from the frontend build
- All other paths fall through to `index.html` (SPA routing)
- API routes (`/api/*`) take precedence via router registration order

---

## 13. Known Limitations & Design Decisions

| Decision | Rationale |
|----------|-----------|
| No authentication | Family tool on a home server. Privacy, not security. |
| SQLite (not Postgres) | Single-user write pattern. No need for concurrent writers. WAL mode handles scheduler + API. |
| No transaction editing UI | Delete and re-create. Edit endpoint exists in the API but no UI form for it. |
| User deletion doesn't cascade | Prevents accidental data loss. Orphaned loans are inaccessible but preserved. |
| Projection runs on every loan list load | Adds `interest_remaining` to each loan response. Acceptable for small loan counts. May need caching if many loans. |
| Daily balance table is a cache | Can always be rebuilt from transactions + rate_history. Never edit directly. |
| Monthly compounding on calendar month end | Matches CIBC PLC behavior. Not every 30 days — actual last day of each month. |
| Payment intervals are fixed day counts | Weekly=7, biweekly=14, monthly=30. Does not account for holidays or weekends. |
