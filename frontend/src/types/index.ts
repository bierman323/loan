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
  interest_remaining?: number | null
  maturity_date?: string | null
  // Borrowing phase: planned monthly draws (projection only) and when repayment begins
  planned_draw_amount: number
  planned_draw_end_date?: string | null
  repayment_start_date?: string | null
  // The payoff date the plan aims for; the Term Shift card compares against it
  planned_maturity_date?: string | null
  in_borrowing_phase: boolean
  // false when the regular payment never pays the loan off
  pays_off?: boolean | null
  balance_at_repayment_start?: number | null
  total_borrowed?: number
  total_repaid?: number
}

export interface LoanCreate {
  name: string
  start_date: string
  initial_amount: number
  regular_payment: number
  payment_frequency: string
  spread: number
  term_months?: number | null
  planned_draw_amount?: number
  planned_draw_end_date?: string | null
  repayment_start_date?: string | null
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
  current_payoff_date?: string | null
  current_pays_off: boolean
  current_total_interest: number
  new_payoff_date?: string | null
  new_pays_off: boolean
  new_total_interest: number
  // null when the current plan never pays off
  interest_saved: number | null
  months_saved: number | null
  balance_at_repayment_start?: number | null
  current_trajectory: ProjectionPoint[]
  new_trajectory: ProjectionPoint[]
}
