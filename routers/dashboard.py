from fastapi import APIRouter, Depends, HTTPException

from core.interest_rarity import get_allocated_student_interest_rarity
from repositories.students import get_available_student_interest_counts
from routers.auth import get_current_user

router: APIRouter = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _require_director_or_admin(current_user: dict) -> None:
    if current_user["account_type"] not in {"admin", "director"}:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get(path="/interests", response_model=dict[str, dict[str, int]])
def get_interest_analysis(
    current_user: dict = Depends(get_current_user),
) -> dict[str, dict[str, int]]:
    _require_director_or_admin(current_user=current_user)
    return get_available_student_interest_counts()

@router.get(path="/interest-rarity", response_model=dict)
def get_interest_rarity_analysis(
    top_matches_per_student: int = 5,
    limit: int | None = 50,
    include_similar_students: bool = False,
    sort: str = "overall_rarity_score",
    current_user: dict = Depends(get_current_user),
) -> dict:
    _require_director_or_admin(current_user=current_user)
    return get_allocated_student_interest_rarity(
        top_matches_per_student=top_matches_per_student,
        limit=limit,
        include_similar_students=include_similar_students,
        sort=sort,
    )
