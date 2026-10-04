from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional
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
PaymentFrequency = Literal["weekly", "biweekly", "monthly"]


class LoanCreate(BaseModel):
    name: str = Field(min_length=1)
    start_date: date
    initial_amount: float = Field(gt=0)
    regular_payment: float = Field(default=0, ge=0)
    payment_frequency: PaymentFrequency = "biweekly"
    spread: float = Field(default=0.9, ge=0)
    term_months: Optional[int] = Field(default=None, gt=0)
    user_id: Optional[int] = None
    # Borrowing phase (optional): planned monthly draws until planned_draw_end_date,
    # no payments until repayment_start_date
    planned_draw_amount: float = Field(default=0, ge=0)
    planned_draw_end_date: Optional[date] = None
    repayment_start_date: Optional[date] = None

    @model_validator(mode="after")
    def dates_not_before_start(self):
        if self.repayment_start_date and self.repayment_start_date < self.start_date:
            raise ValueError("Repayment start cannot be before the loan start date")
        if self.planned_draw_end_date and self.planned_draw_end_date < self.start_date:
            raise ValueError("Last planned draw cannot be before the loan start date")
        return self


class LoanUpdate(BaseModel):
    """
    Only fields present in the request are changed. Sending null clears the nullable
    fields (term_months, planned_draw_end_date, repayment_start_date).
    """
    name: Optional[str] = Field(default=None, min_length=1)
    regular_payment: Optional[float] = Field(default=None, gt=0)
    payment_frequency: Optional[PaymentFrequency] = None
    spread: Optional[float] = Field(default=None, ge=0)
    term_months: Optional[int] = Field(default=None, gt=0)
    planned_draw_amount: Optional[float] = Field(default=None, ge=0)
    planned_draw_end_date: Optional[date] = None
    repayment_start_date: Optional[date] = None


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
    maturity_date: Optional[date] = None
    planned_draw_amount: float = 0
    planned_draw_end_date: Optional[date] = None
    repayment_start_date: Optional[date] = None
    planned_maturity_date: Optional[date] = None
    in_borrowing_phase: bool = False
    # False when the regular payment never pays the loan off
    pays_off: Optional[bool] = None
    balance_at_repayment_start: Optional[float] = None
    total_borrowed: Optional[float] = None
    total_repaid: Optional[float] = None


# --- Transactions ---
def _reject_zero_amount(amount: float | None) -> float | None:
    if amount is not None and amount == 0:
        raise ValueError("Amount cannot be zero (negative = payment, positive = draw)")
    return amount


class TransactionCreate(BaseModel):
    loan_id: int
    date: date
    amount: float
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_not_zero(cls, amount: float) -> float:
        return _reject_zero_amount(amount)


class TransactionUpdate(BaseModel):
    date: Optional[date] = None
    amount: Optional[float] = None
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_not_zero(cls, amount: float | None) -> float | None:
        return _reject_zero_amount(amount)


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
    prime_rate: float = Field(ge=0)
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
    extra_payment: float = Field(default=0, ge=0)
    extra_payment_date: Optional[date] = None
    extra_recurring: float = Field(default=0, ge=0)


class ProjectionPoint(BaseModel):
    date: date
    balance: float
    cumulative_interest: float


class ProjectionResponse(BaseModel):
    current_payoff_date: Optional[date] = None
    current_pays_off: bool
    current_total_interest: float
    new_payoff_date: Optional[date] = None
    new_pays_off: bool
    new_total_interest: float
    # None when the current plan never pays off, so there is nothing to compare against
    interest_saved: Optional[float] = None
    months_saved: Optional[float] = None
    balance_at_repayment_start: Optional[float] = None
    current_trajectory: list[ProjectionPoint]
    new_trajectory: list[ProjectionPoint]
