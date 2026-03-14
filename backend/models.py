from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


# --- Users ---
class UserCreate(BaseModel):
    name: str


class UserResponse(BaseModel):
    id: int
    name: str
    token: str
    created_at: Optional[datetime] = None


# --- Loans ---
class LoanCreate(BaseModel):
    name: str
    start_date: date
    initial_amount: float
    regular_payment: float = 0
    payment_frequency: str = "biweekly"
    spread: float = 0.9
    term_months: Optional[int] = None
    user_id: Optional[int] = None


class LoanUpdate(BaseModel):
    name: Optional[str] = None
    regular_payment: Optional[float] = None
    payment_frequency: Optional[str] = None
    spread: Optional[float] = None
    term_months: Optional[int] = None


class LoanResponse(BaseModel):
    id: int
    name: str
    start_date: date
    initial_amount: float
    regular_payment: float
    payment_frequency: str
    spread: float
    term_months: Optional[int] = None
    created_at: Optional[datetime] = None
    current_balance: Optional[float] = None
    daily_interest: Optional[float] = None
    effective_rate: Optional[float] = None
    interest_paid: Optional[float] = None
    interest_remaining: Optional[float] = None


# --- Transactions ---
class TransactionCreate(BaseModel):
    loan_id: int
    date: date
    amount: float
    description: Optional[str] = None


class TransactionUpdate(BaseModel):
    date: Optional[date] = None
    amount: Optional[float] = None
    description: Optional[str] = None


class TransactionResponse(BaseModel):
    id: int
    loan_id: int
    date: date
    amount: float
    description: Optional[str] = None
    created_at: Optional[datetime] = None


# --- Rates ---
class RateCreate(BaseModel):
    effective_date: date
    prime_rate: float
    source: str = "manual"


class RateResponse(BaseModel):
    id: int
    effective_date: date
    prime_rate: float
    source: str
    fetched_at: Optional[datetime] = None


# --- Daily Balance ---
class DailyBalanceResponse(BaseModel):
    loan_id: int
    date: date
    opening_balance: float
    interest_accrued: float
    closing_balance: float
    effective_rate: float


# --- Projections ---
class ProjectionRequest(BaseModel):
    loan_id: int
    extra_payment: float = 0
    extra_payment_date: Optional[date] = None
    extra_recurring: float = 0


class ProjectionPoint(BaseModel):
    date: date
    balance: float
    cumulative_interest: float


class ProjectionResponse(BaseModel):
    current_payoff_date: Optional[date] = None
    current_total_interest: float
    new_payoff_date: Optional[date] = None
    new_total_interest: float
    interest_saved: float
    months_saved: float
    current_trajectory: list[ProjectionPoint]
    new_trajectory: list[ProjectionPoint]
