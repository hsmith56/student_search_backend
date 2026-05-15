from fastapi import APIRouter, Depends, HTTPException

from repositories.students import get_available_student_interest_counts
from routers.auth import get_current_user

router: APIRouter = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _require_director_or_admin(current_user: dict) -> None:
    if current_user["account_type"] not in {"admin", "director"}:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get(path="/interests", response_model=dict[str, int])
def get_interest_analysis(
    current_user: dict = Depends(get_current_user),
) -> dict[str, int]:
    _require_director_or_admin(current_user=current_user)
    return get_available_student_interest_counts()
