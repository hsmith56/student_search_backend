from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from recommendation_engine import get_recommendations
from routers.auth import get_current_user

router: APIRouter = APIRouter(prefix="/recommendation", tags=["recommendation"])


class RecommendationRequest(BaseModel):
    usahsid: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    compare: str = Field(default="allocated", min_length=1)
    priority_interests: list[str] = Field(default_factory=list)
    gender: int = Field(default=0, ge=0, le=2)


class RecommendationItem(BaseModel):
    app_id: int
    usahsid: str
    first_name: str
    placement_status: str
    score: float
    interest_overlap: int
    state_overlap: int
    reasons: dict[str, Any]


@router.post(path="/", response_model=list[RecommendationItem])
def create_recommendations(
    payload: RecommendationRequest,
    current_user: dict = Depends(get_current_user),
) -> list[RecommendationItem]:
    try:
        recommendations = get_recommendations(
            usahsid=payload.usahsid,
            n=payload.limit,
            compare=payload.compare,
            username=current_user["username"],
            priority_interests=payload.priority_interests,
            gender=payload.gender,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail.startswith("No student found") else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return [RecommendationItem.model_validate(item.__dict__) for item in recommendations]
