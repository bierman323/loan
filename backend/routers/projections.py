from fastapi import APIRouter
from backend.models import ProjectionRequest, ProjectionResponse
from backend.services.projection_engine import project_payoff

router = APIRouter(prefix="/api/projections", tags=["projections"])


@router.post("", response_model=ProjectionResponse)
def calculate_projection(req: ProjectionRequest):
    result = project_payoff(
        loan_id=req.loan_id,
        extra_payment=req.extra_payment,
        extra_payment_date=req.extra_payment_date,
        extra_recurring=req.extra_recurring,
    )
    return ProjectionResponse(**result)
