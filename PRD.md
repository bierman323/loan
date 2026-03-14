# Loan Tracker — Product Requirements Document

## 1. Problem Statement

A father has lent money to his daughter for a car using his CIBC Personal Line of Credit (PLC). The PLC charges daily interest at prime + a spread, compounded monthly. He needs a way to:

- Know the exact balance owed on any given day
- Record payments as they happen and see the balance update accurately
- Understand how much of the cost is going to interest vs. principal
- See what happens if extra payments are made (how much interest is saved, how much sooner the loan is paid off)
- Allow the daughter to see her own loan balance and payment history
- Handle life changes (job loss, raises) by adjusting payment amounts or extending the term without losing track of what's already been paid

The existing approach (spreadsheets or mental math) is error-prone, especially with variable prime rates and the daily accrual / monthly compounding model.

## 2. Target Users

| User | Needs |
|------|-------|
| **Dad (lender)** | Accurate balance tracking, payment recording, rate management, multiple loan support (may lend to other family members) |
| **Daughter (borrower)** | View her balance, see payment history, understand payoff timeline, model "what if I pay extra" scenarios |

Both users share the same home server. They need to see their own data without seeing each other's (basic privacy, not security).

## 3. User Stories

### Account & Access

- **As a user**, I can create a profile with just my name so I can start tracking loans without any signup friction.
- **As a user**, I can switch between profiles on a shared device so multiple family members can use the same server.
- **As a user**, my session persists across browser refreshes so I don't have to re-select myself every time.

### Loan Setup

- **As a lender**, I can create a new loan with a name, start date, amount, and interest spread so the system begins tracking from day one.
- **As a lender**, I can specify either a payment amount or a term length and have the system calculate the other, so I don't need to do the amortization math myself.
- **As a lender**, I can track multiple loans (car, furniture, etc.) in separate tabs so each is independent.

### Payment Tracking

- **As a user**, I can record a payment with a date and amount so the balance updates accurately from that date forward.
- **As a user**, the payment form defaults to the regular payment amount so I can record routine payments with one click.
- **As a user**, I can delete a payment if it was entered incorrectly, and the balance recalculates automatically.
- **As a user**, I can see a chronological list of all payments with dates and descriptions.

### Balance & Interest Visibility

- **As a borrower**, I can see my current balance at a glance so I know exactly what I owe today.
- **As a user**, I can see how much total interest has been paid to date so I understand the cost of borrowing.
- **As a user**, I can see how much interest remains (projected) so I understand the total remaining cost.
- **As a user**, I can see the current effective interest rate (prime + spread) and the daily interest accrual amount.
- **As a user**, I can see a chart of my balance over time to visualize progress.
- **As a user**, I can see how much principal I've paid down and what percentage of the original loan that represents.

### Rate Management

- **As a lender**, the system automatically fetches the current Bank of Canada prime rate daily so I don't have to update it manually.
- **As a lender**, I can manually override the prime rate for a specific date if the automatic fetch is wrong or delayed.
- **As a lender**, I can see a history of rate changes and their sources (automatic vs. manual).

### Scenario Planning

- **As a borrower**, I can enter a hypothetical lump sum payment and see how much interest I'd save and how many months sooner I'd be paid off.
- **As a borrower**, I can enter a hypothetical increase to my regular payment amount and see the long-term impact.
- **As a user**, I can see a side-by-side chart comparing my current trajectory with the hypothetical scenario.

### Life Changes

- **As a user**, I can change my regular payment amount mid-loan (e.g., after a job loss) and have the remaining term recalculate based on my current balance and new payment.
- **As a user**, I can change my loan term mid-loan (e.g., extend by 12 months) and have the required payment recalculate based on my current balance.
- **As a user**, I can change my payment frequency (weekly ↔ biweekly ↔ monthly) if my pay schedule changes.
- **As a user**, all my past payment history is preserved when I make these adjustments — nothing is lost or rewritten.

### Deployment

- **As an admin**, I can run the app in Docker on my home server with a single `docker compose up` command.
- **As an admin**, the database persists on the host filesystem so data survives container rebuilds.
- **As an admin**, the app runs on a single port (8080) serving both the UI and API.

## 4. Functional Requirements

### FR-1: Interest Calculation

The system must calculate interest using the CIBC PLC model:

- **Daily accrual**: `balance × (prime_rate + spread) / 100 / 365`
- **Monthly compounding**: Accumulated daily interest is added to the principal on the last calendar day of each month.
- **Variable rate**: When the prime rate changes, interest from that date forward uses the new rate. Historical balances remain as calculated.
- **Precision**: Calculations must use decimal arithmetic (not floating point) to avoid rounding drift over years of daily accrual.

### FR-2: Balance Recomputation

When a payment is added, edited, or deleted — or when a rate changes — the system must recompute all daily balances from the affected date forward. This ensures retroactive corrections are reflected accurately through the entire history.

### FR-3: Payment/Term Duality

The system must support two entry modes for loan setup:
- Enter payment amount → system calculates term
- Enter term → system calculates payment

When adjusting mid-loan, the same calculation must use the **current balance** (not the original amount) to determine the remaining term or required payment.

### FR-4: Automatic Rate Fetching

The system must fetch the Bank of Canada prime rate daily from the Valet API. If the API is unavailable, it must fall back to the most recent stored rate without error. Rate fetching must also occur on application startup.

### FR-5: Projection Engine

The system must simulate future payoff day-by-day using the same interest model as the balance engine. It must support one-time lump sum payments and recurring extra payments, producing both the current and modified trajectories for comparison.

### FR-6: Multi-User Isolation

Each user's loans must be visible only to that user. The system must use a token-based identification mechanism stored in the browser without requiring passwords or authentication.

### FR-7: Data Persistence

All data must be stored in a SQLite database that persists across container restarts via a Docker volume mount. Schema migrations must be non-destructive (add columns only, never drop data).

## 5. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| **Deployment** | Single Docker container, single `docker compose up` command |
| **Performance** | Balance recomputation for a 5-year loan (1,825 days) should complete in under 2 seconds |
| **Data safety** | SQLite WAL mode for concurrent scheduler + API access without corruption |
| **Browser support** | Modern browsers (Chrome, Firefox, Safari). No IE support. |
| **Mobile** | Responsive layout (Tailwind CSS), usable on phone screens |
| **Availability** | `restart: unless-stopped` in Docker Compose for automatic recovery |

## 6. Out of Scope

These were explicitly not built:

- **Authentication / passwords** — not needed for a family tool on a private network
- **Multi-currency** — all amounts are CAD
- **Amortization schedules** — the daily balance table serves this purpose but there's no formatted amortization schedule export
- **Email/SMS notifications** — no payment reminders or alerts
- **Multiple rate spreads per loan over time** — spread is per-loan, not time-varying
- **Payment import** (CSV, bank feed) — payments are entered manually
- **Audit log** — no history of who changed what
- **Transaction editing UI** — API supports it, but the UI only offers delete-and-recreate

## 7. UI Layout

```
┌──────────────────────────────────────────────────────────┐
│  Loan Tracker                              [User ▼]      │
│  Track balances, payments, and interest                  │
├──────────────────────────────────────────────────────────┤
│  [Car Loan] [Furniture Loan] [+ New Loan]                │
├──────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Payment  │  │Frequency │  │  Term    │  ← Editable   │
│  │ $239.13  │  │ Weekly   │  │ 3 yr    │    (hover →    │
│  │ Weekly   │  │ $239/per │  │ 36 mo   │    "Adjust")   │
│  └──────────┘  └──────────┘  └──────────┘               │
│  ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐         │
│  │Balance │ │Interest│ │ Interest │ │  Rate  │         │
│  │$34,650 │ │ Paid   │ │Remaining │ │ 4.95%  │         │
│  │        │ │ $5.17  │ │ $2,640   │ │P+0.5%  │         │
│  └────────┘ └────────┘ └──────────┘ └────────┘         │
│  ┌────────┐ ┌──────────┐                                │
│  │ Daily  │ │Principal │                                │
│  │Interest│ │  Paid    │                                │
│  │ $4.70  │ │  $0.00   │                                │
│  └────────┘ └──────────┘                                │
├──────────────────────────────────────────────────────────┤
│  Record Payment                                          │
│  [Date] [Amount (blank=$239.13)] [Description] [Record]  │
├──────────────────────────────────────────────────────────┤
│  Payment History (sortable table)                        │
│  Date         Amount        Description        [×]       │
│  Mar 13       -$239.13      Initial payment    [×]       │
├──────────────────────────────────────────────────────────┤
│  Balance Over Time (line chart)                          │
│  ╭──────────────╮                                        │
│  │ ╲            │                                        │
│  │   ╲──────    │                                        │
│  ╰──────────────╯                                        │
├──────────────────────────────────────────────────────────┤
│  What-If Scenario Calculator                             │
│  [Extra lump sum $] [Extra per payment $] [Calculate]    │
│  Interest Saved: $157 | Months Saved: 0.9 | Payoff: Feb │
│  ╭──────────────╮                                        │
│  │ ──current    │  (dual line comparison chart)          │
│  │ ──scenario   │                                        │
│  ╰──────────────╯                                        │
├──────────────────────────────────────────────────────────┤
│  Prime Rate History                                      │
│  [+ Manual Override]                                     │
│  Date         Rate     Source                            │
│  Mar 14       4.45%    Bank of Canada                    │
└──────────────────────────────────────────────────────────┘
```

## 8. Data Model Summary

| Entity | Key Fields | Relationships |
|--------|-----------|---------------|
| **User** | name, token (UUID) | Has many Loans |
| **Loan** | name, start_date, initial_amount, regular_payment, frequency, spread, term_months | Belongs to User. Has many Transactions. Has many DailyBalances (computed). |
| **Transaction** | date, amount (neg=payment, pos=disbursement), description | Belongs to Loan. Cascade delete with loan. |
| **RateHistory** | effective_date, prime_rate, source | Global (not per-loan or per-user). |
| **DailyBalance** | date, opening_balance, interest_accrued, closing_balance, effective_rate | Computed cache. Belongs to Loan. Rebuildable from Transactions + RateHistory. |

## 9. External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Bank of Canada Valet API | Daily prime rate | Falls back to most recent stored rate. No error surfaced to user. |

## 10. Acceptance Criteria

### Loan Lifecycle
- [ ] Create a loan with name, date, amount, and term → payment is calculated and displayed
- [ ] Create a loan with name, date, amount, and payment → term is calculated and displayed
- [ ] Record a payment → balance decreases; daily interest recalculates
- [ ] Record a backdated payment → all balances from that date forward recalculate
- [ ] Delete a payment → balance and history revert as if payment never existed
- [ ] Adjust payment amount mid-loan → term recalculates from current balance
- [ ] Adjust term mid-loan → payment recalculates from current balance

### Interest Accuracy
- [ ] Daily interest matches: `balance × (prime + spread) / 100 / 365`
- [ ] Interest compounds on the last day of each calendar month
- [ ] Rate changes mid-month are reflected in daily accrual from the change date forward
- [ ] Total interest paid = sum of all daily accruals in balance history

### Projections
- [ ] "What if I pay $1,000 extra?" shows reduced payoff date and interest saved
- [ ] "What if I pay $100 extra per payment?" shows long-term savings
- [ ] Comparison chart shows both trajectories
- [ ] Projected payoff date aligns with the loan's term

### Multi-User
- [ ] User A cannot see User B's loans
- [ ] Switching users loads the correct loan data
- [ ] Browser refresh preserves the current user session

### Deployment
- [ ] `docker compose up --build` starts the app at localhost:8080
- [ ] `docker compose down && docker compose up` preserves all data
- [ ] Creating a second loan tab works independently of the first

## 11. Future Considerations

Things that were discussed or could be valuable but are not in the current build:

- **Payment reminders** — email or push notification when a payment is due
- **Amortization schedule export** — PDF or CSV of the full payment schedule
- **Rate spread changes over time** — track spread changes like rate changes
- **Transaction edit UI** — inline editing of payment date/amount (API exists, UI doesn't)
- **Bulk payment import** — CSV upload for catching up on historical payments
- **Audit trail** — log of all changes for accountability
- **Mobile app** — native app for quick payment recording
