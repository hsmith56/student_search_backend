from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from repositories.user_signup import (
    create_signup_request,
    list_signup_requests_for_user,
)
from routers.auth import get_current_user

router: APIRouter = APIRouter(prefix="/rpm", tags=["rpm"])


def _require_rpm_or_admin(current_user: dict) -> None:
    if current_user["account_type"] not in {"admin", "rpm"}:
        raise HTTPException(status_code=403, detail="Forbidden")


class SignupRequestCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: str | None = None
    states: list[str]
    account_type: Literal["lc", "rpm"]


class SignupRequestItem(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None = None
    states: list[str]
    account_type: Literal["lc", "rpm"]
    code_used: bool
    submitter_id: str
    created_at: str
    used_at: str | None = None


class SignupRequestCreated(SignupRequestItem):
    auth_code: str


@router.post(path="/register", response_model=SignupRequestCreated, status_code=201)
def create_rpm_signup_request(
    payload: SignupRequestCreate,
    current_user: dict = Depends(get_current_user),
) -> SignupRequestCreated:
    _require_rpm_or_admin(current_user=current_user)
    try:
        created = create_signup_request(
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=payload.email.strip() if isinstance(payload.email, str) else None,
            states=payload.states,
            account_type=payload.account_type,
            submitter_id=current_user["id"],
        )
        return SignupRequestCreated(**created)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(path="/register", response_model=list[SignupRequestItem])
def get_rpm_signup_requests(
    current_user: dict = Depends(get_current_user),
) -> list[SignupRequestItem]:
    _require_rpm_or_admin(current_user=current_user)
    rows = list_signup_requests_for_user(
        requester_id=current_user["id"],
        requester_role=current_user["account_type"],
    )
    return [SignupRequestItem(**row) for row in rows]
