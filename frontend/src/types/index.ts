export interface Loan {
  id: number
  name: string
  start_date: string
  initial_amount: number
  regular_payment: number
  payment_frequency: string
  spread: number
  term_months?: number | null
  created_at?: string
  current_balance?: number
  daily_interest?: number
  effective_rate?: number
  interest_paid?: number
  interest_remaining?: number
  maturity_date?: string | null
}

export interface LoanCreate {
  name: string
  start_date: string
  initial_amount: number
  regular_payment: number
  payment_frequency: string
  spread: number
  term_months?: number | null
}

export interface Transaction {
  id: number
  loan_id: number
  date: string
  amount: number
  description?: string
  created_at?: string
}

export interface TransactionCreate {
  loan_id: number
  date: string
  amount: number
  description?: string
}

export interface Rate {
  id: number
  effective_date: string
  prime_rate: number
  source: string
  fetched_at?: string
}

export interface DailyBalance {
  loan_id: number
  date: string
  opening_balance: number
  interest_accrued: number
  closing_balance: number
  effective_rate: number
}

export interface ProjectionPoint {
  date: string
  balance: number
  cumulative_interest: number
}

export interface ProjectionResult {
  current_payoff_date?: string
  current_total_interest: number
  new_payoff_date?: string
  new_total_interest: number
  interest_saved: number
  months_saved: number
  current_trajectory: ProjectionPoint[]
  new_trajectory: ProjectionPoint[]
}
