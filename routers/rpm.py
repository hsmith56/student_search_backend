from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from repositories.user_signup import (
    create_signup_request,
    delete_signup_request_by_id,
    list_signup_requests_for_user,
    update_signup_request_for_user,
)
from repositories.users import (
    get_user_with_states_by_id,
    update_user_placing_states_by_id,
    update_user_submitter_id_by_id,
    read_user,
)
from routers.auth import get_current_user

router: APIRouter = APIRouter(prefix="/rpm", tags=["rpm"])


def _require_rpm_or_admin(current_user: dict) -> None:
    if current_user["account_type"] not in {"admin", "rpm"}:
        raise HTTPException(status_code=403, detail="Forbidden")


def _require_admin(current_user: dict) -> None:
    if current_user["account_type"] != "admin":
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
    auth_code: str | None = None
    notes_text: str | None = None


class SignupRequestCreated(SignupRequestItem):
    auth_code: str


class SignupRequestUpdate(BaseModel):
    states: list[str] | None = None
    notes_text: str | None = None


class AdminGetUserItem(BaseModel):
    id: str
    username: str
    first_name: str
    account_type: Literal["admin", "rpm", "lc"]
    states: list[str]
    submitter_id: str | None = None


class AdminPatchRequest(BaseModel):
    states: list[str] | None = None
    submitter_id: str | None = None


def _to_admin_user_item(payload: dict) -> AdminGetUserItem:
    submitter_id = payload.get("submitter_id")
    if payload["account_type"] != "lc":
        submitter_id = None

    return AdminGetUserItem(
        id=payload["id"],
        username=payload["username"],
        first_name=payload["first_name"],
        account_type=payload["account_type"],
        states=payload["placing_states"],
        submitter_id=submitter_id,
    )


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


@router.patch(path="/register/{signup_id}", response_model=SignupRequestItem)
def update_rpm_signup_request(
    signup_id: int,
    payload: SignupRequestUpdate,
    current_user: dict = Depends(get_current_user),
) -> SignupRequestItem:
    _require_rpm_or_admin(current_user=current_user)

    update_states = "states" in payload.model_fields_set
    update_notes = "notes_text" in payload.model_fields_set
    if update_states is False and update_notes is False:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    updated = update_signup_request_for_user(
        signup_id=signup_id,
        requester_id=current_user["id"],
        requester_role=current_user["account_type"],
        states=payload.states,
        notes_text=payload.notes_text,
        update_states=update_states,
        update_notes=update_notes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Signup request not found")

    return SignupRequestItem(**updated)


@router.get(
    path="/admin_get",
    response_model=list[SignupRequestItem],
)
def admin_get(current_user: dict = Depends(get_current_user)) -> list[SignupRequestItem]:
    _require_admin(current_user=current_user)
    rows = list_signup_requests_for_user(
        requester_id=current_user["id"],
        requester_role="admin",
    )
    return [SignupRequestItem(**row) for row in rows]


@router.patch(
    path="/admin_patch/{user_id}",
    response_model=AdminGetUserItem,
    response_model_exclude_none=True,
)
def admin_patch(
    user_id: str,
    payload: AdminPatchRequest,
    current_user: dict = Depends(get_current_user),
) -> AdminGetUserItem:
    _require_admin(current_user=current_user)

    update_states = "states" in payload.model_fields_set
    update_submitter_id = "submitter_id" in payload.model_fields_set
    if update_states is False and update_submitter_id is False:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    user = get_user_with_states_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if update_submitter_id:
        if user["account_type"] != "lc":
            raise HTTPException(
                status_code=400,
                detail="submitter_id can only be updated for local coordinator accounts",
            )
        if payload.submitter_id is not None:
            submitter = read_user(user_id=payload.submitter_id)
            if submitter is None:
                raise HTTPException(status_code=400, detail="submitter_id user not found")
            if submitter["account_type"] not in {"admin", "rpm"}:
                raise HTTPException(
                    status_code=400,
                    detail="submitter_id must reference an admin or rpm user",
                )

        submitter_updated = update_user_submitter_id_by_id(
            user_id=user_id, submitter_id=payload.submitter_id
        )
        if submitter_updated is False:
            raise HTTPException(status_code=404, detail="User not found")

    if update_states:
        states_updated = update_user_placing_states_by_id(
            user_id=user_id, states=payload.states or []
        )
        if states_updated is False:
            raise HTTPException(status_code=404, detail="User not found")

    user = get_user_with_states_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_admin_user_item(payload=user)


@router.delete(path="/admin_delete/{signup_id}")
def admin_delete(
    signup_id: int, current_user: dict = Depends(get_current_user)
) -> dict[str, str]:
    _require_admin(current_user=current_user)
    deleted = delete_signup_request_by_id(signup_id=signup_id)
    if deleted is False:
        raise HTTPException(status_code=404, detail="Signup request not found")
    return {"message": "Signup request deleted"}
