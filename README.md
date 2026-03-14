# Loan Tracker

A web application for tracking personal loans with daily interest accrual and monthly compounding, built for the CIBC Personal Line of Credit (PLC) interest model.

Designed for a parent lending money to family members — track the real balance, record payments, and project payoff scenarios with accurate interest calculations.

## Features

- **Multi-user support** — token-based user switching, no passwords; each user sees only their own loans
- **Multi-loan tabs** — track multiple loans independently (car loan, furniture loan, etc.)
- **Accurate interest calculation** — daily accrual at (prime + spread) / 365, compounded monthly on the last day of each month, using Python `Decimal` for precision
- **Automatic rate fetching** — pulls the current Bank of Canada prime rate daily via the [Valet API](https://www.bankofcanada.ca/valet/observations/V80691311/json?recent=1)
- **Payment recording** — record payments with date and description; balance recalculates from the affected date forward
- **Adjustable terms** — change payment amount or term mid-loan (e.g., job loss); the other recalculates from the current balance, preserving all existing payments
- **What-if scenarios** — "What if I pay $X extra?" calculator showing interest saved, months saved, and comparison chart
- **Balance history chart** — line chart of balance over time (Recharts)
- **Interest dashboard** — current balance, interest paid to date, interest remaining, effective rate, daily interest, principal paid
- **Docker deployment** — single container, SQLite data persisted on host via volume mount

## Quick Start

### Docker (recommended)

```bash
docker compose up --build
```

App runs at **http://localhost:8080**. Data persists in `./data/loan_tracker.db`.

### Local Development

**Backend:**

```bash
pip3 install -r backend/requirements.txt
DATABASE_PATH=./data/loan_tracker.db python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

**Frontend (dev server with hot reload):**

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `localhost:8080`.

**Frontend (production build):**

```bash
cd frontend
npm run build
# Copy build output to where the backend serves it:
cp -r dist ../static
```

## Architecture

```
┌─────────────────────────────┐
│  Browser (React + Tailwind) │
│  Token in localStorage      │
└──────────┬──────────────────┘
           │ /api/*
┌──────────▼──────────────────┐
│  FastAPI (Python 3.12)      │
│  ├─ routers/                │
│  │   ├─ users.py            │
│  │   ├─ loans.py            │
│  │   ├─ transactions.py     │
│  │   ├─ rates.py            │
│  │   └─ projections.py      │
│  └─ services/               │
│      ├─ interest_engine.py  │  ← Core: daily accrual + monthly compounding
│      ├─ projection_engine.py│  ← What-if simulator
│      ├─ rate_fetcher.py     │  ← Bank of Canada API client
│      └─ scheduler.py        │  ← APScheduler: daily rate fetch
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│  SQLite (WAL mode)          │
│  ./data/loan_tracker.db     │
└─────────────────────────────┘
```

## Interest Calculation Model

This matches how the CIBC Personal Line of Credit charges interest:

```
For each day from loan start to today:
  1. effective_rate = prime_rate + spread  (e.g., 4.45% + 0.9% = 5.35%)
  2. Apply any transactions on this date (negative = payment, positive = disbursement)
  3. daily_interest = balance × (effective_rate / 100) / 365
  4. Accumulate daily interest into a monthly bucket
  5. On the last day of the month → add accumulated interest to principal (compounding)
  6. Store the daily balance record
```

When a payment is added, edited, or deleted, the engine recalculates from the affected date forward.

## Database Schema

### `users`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Display name |
| token | TEXT UNIQUE | UUID hex, stored in browser localStorage |

### `loans`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Display name ("Car Loan") |
| start_date | DATE | Disbursement date |
| initial_amount | REAL | Original amount borrowed |
| regular_payment | REAL | Expected payment amount |
| payment_frequency | TEXT | "weekly", "biweekly", "monthly" |
| spread | REAL | Percentage above prime (default 0.9) |
| term_months | INTEGER | Loan term; auto-calculated if omitted |
| user_id | INTEGER FK | → users.id |

### `transactions`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| loan_id | INTEGER FK | → loans.id |
| date | DATE | When payment was deposited |
| amount | REAL | Negative = payment, positive = disbursement |
| description | TEXT | Optional note |

### `rate_history`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| effective_date | DATE | Date rate took effect |
| prime_rate | REAL | e.g., 4.45 |
| source | TEXT | "bank_of_canada_api" or "manual" |

### `daily_balances` (computed cache)
| Column | Type | Notes |
|--------|------|-------|
| loan_id | INTEGER | Composite PK with date |
| date | DATE | |
| opening_balance | REAL | |
| interest_accrued | REAL | Daily interest |
| closing_balance | REAL | |
| effective_rate | REAL | Annual rate (prime + spread) |

## API Reference

All endpoints are prefixed with `/api`. Loan endpoints filter by user via the `X-User-Token` header.

### Users
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users` | List all users |
| POST | `/api/users` | Create user `{ name }` → returns `{ id, name, token }` |
| GET | `/api/users/by-token/{token}` | Look up user by token |

### Loans
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/loans` | List loans for current user |
| POST | `/api/loans` | Create loan (auto-calculates payment or term) |
| GET | `/api/loans/{id}` | Get loan with computed fields |
| PATCH | `/api/loans/{id}` | Update loan (adjusting payment recalculates term and vice versa) |
| DELETE | `/api/loans/{id}` | Delete loan and all related data |
| GET | `/api/loans/{id}/balances` | Get daily balance history |

### Transactions
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/transactions?loan_id=` | List transactions |
| POST | `/api/transactions` | Record payment (triggers balance recalculation) |
| PATCH | `/api/transactions/{id}` | Edit transaction |
| DELETE | `/api/transactions/{id}` | Delete transaction |

### Rates
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rates` | Rate history |
| POST | `/api/rates` | Manual rate override |
| DELETE | `/api/rates/{id}` | Delete rate entry |

### Projections
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projections` | Calculate payoff scenarios `{ loan_id, extra_payment, extra_recurring }` |

## File Structure

```
loan/
├── README.md                         ← You are here
├── CLAUDE.md                         ← Context for Claude Code sessions
├── Dockerfile                        ← Multi-stage: Node build → Python runtime
├── docker-compose.yml                ← Single service, volume mount for data
├── .gitignore
├── .dockerignore
├── backend/
│   ├── requirements.txt              ← fastapi, uvicorn, httpx, apscheduler, pydantic
│   ├── main.py                       ← App entry, CORS, static mount, lifespan
│   ├── config.py                     ← DB path, spread, API URL
│   ├── database.py                   ← SQLite setup, schema, migrations
│   ├── models.py                     ← Pydantic request/response schemas
│   ├── routers/
│   │   ├── users.py                  ← User CRUD
│   │   ├── loans.py                  ← Loan CRUD + payment/term recalculation
│   │   ├── transactions.py           ← Payment recording + balance recomputation
│   │   ├── rates.py                  ← Rate history + manual override
│   │   └── projections.py            ← Scenario calculator endpoint
│   └── services/
│       ├── interest_engine.py        ← Core: daily interest calc, balance recomputation
│       ├── projection_engine.py      ← What-if payoff simulator
│       ├── rate_fetcher.py           ← Bank of Canada API client
│       └── scheduler.py             ← APScheduler: daily rate fetch + interest accrual
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx                   ← Root with user context + tab routing
│       ├── index.css
│       ├── api/client.ts             ← Axios wrapper with token interceptor
│       ├── types/index.ts            ← TypeScript interfaces
│       └── components/
│           ├── UserSwitcher.tsx       ← User dropdown (create/switch/sign out)
│           ├── LoanTabs.tsx          ← Dynamic tab bar with loan creation form
│           ├── Dashboard.tsx         ← Editable payment/term/frequency + metrics cards
│           ├── PaymentForm.tsx       ← Record payment (prefilled with regular amount)
│           ├── PaymentHistory.tsx    ← Sortable transaction table
│           ├── BalanceChart.tsx      ← Recharts line chart
│           ├── ScenarioCalc.tsx      ← What-if calculator with comparison chart
│           ├── RateHistory.tsx       ← Rate timeline + manual override
│           └── Tooltip.tsx           ← Reusable hover tooltip
└── data/                             ← Docker volume mount (gitignored)
    └── loan_tracker.db
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `DATABASE_PATH` | `data/loan_tracker.db` | Path to SQLite database file |

The spread (percentage above prime) is set per-loan at creation time and can be adjusted later.

## User System

There is no authentication. Users are identified by a UUID token stored in the browser's `localStorage`. This provides basic privacy between family members sharing the same server — each user only sees their own loans.

- Create a user → a token is generated and saved to the browser
- Switch users → pick from the dropdown, token swaps in localStorage
- All API calls include the token as an `X-User-Token` header

## Adjusting Payments Mid-Loan

If circumstances change (job loss, windfall, etc.), hover over the **Payment**, **Frequency**, or **Term** cards in the dashboard and click "Adjust":

- **Change payment amount** → term recalculates from current balance
- **Change term** → payment recalculates from current balance
- **Change frequency** → schedule updates

All existing payment history is preserved. The recalculation uses today's actual balance, not the original loan amount.

## Development Notes

### Adding a new field to loans

1. Add the column to the `SCHEMA` in `backend/database.py`
2. Add a migration in `init_db()` using `ALTER TABLE` (for existing databases)
3. Add the field to `LoanCreate`, `LoanUpdate`, and `LoanResponse` in `backend/models.py`
4. Update `backend/routers/loans.py` to handle it in create/update
5. Add the field to the `Loan` and `LoanCreate` interfaces in `frontend/src/types/index.ts`
6. Update relevant components

### Rebuilding after changes

```bash
# Backend changes: just restart uvicorn (or the Docker container)
# Frontend changes:
cd frontend && npm run build
cp -r dist ../static

# Or with Docker:
docker compose up --build
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Database | SQLite (WAL mode) |
| Frontend | React 18, TypeScript, Vite |
| Styling | Tailwind CSS |
| Charts | Recharts |
| HTTP Client | Axios (frontend), httpx (backend) |
| Scheduler | APScheduler |
| Deployment | Docker (multi-stage build) |

## Claude Code Notes

This project was built entirely with base Claude Code tools (no custom plugins, skills, subagents, or slash commands). The `.claude/settings.local.json` file contains project-level permission overrides for convenience during development — it is not required to run the application.
