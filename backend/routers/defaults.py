from fastapi import APIRouter
from backend.config import DEFAULT_SPREAD

router = APIRouter(prefix="/api/defaults", tags=["defaults"])


@router.get("")
def get_defaults():
    """Defaults for the New Loan form, so config.py is the only place to change them."""
    return {"spread": DEFAULT_SPREAD}
