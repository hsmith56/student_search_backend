import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from repositories.user_notes import (
    get_user_note,
    get_user_notes_for_owner,
    upsert_user_note,
)
from repositories.users import (
    create_pending_signup_user,
    delete_user_by_id,
    get_signup_user_for_manager,
    list_all_users_with_states,
    get_user_with_states_by_id,
    list_signup_users_for_manager,
    read_user,
    update_user_manager_id_by_id,
    update_user_placing_states_by_id,
)
from routers.auth import get_current_user
from utils.signup_email import send_signup_invitation_email

router: APIRouter = APIRouter(prefix="/rpm", tags=["rpm"])
logger = logging.getLogger(__name__)


def _require_rpm_or_admin(current_user: dict) -> None:
    if current_user["account_type"] not in {"admin", "rpm"}:
        raise HTTPException(status_code=403, detail="Forbidden")


def _require_admin(current_user: dict) -> None:
    if current_user["account_type"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")


def _normalize_optional_text(value: str | None) -> str | None:
    if isinstance(value, str) is False:
        return None
    normalized = value.strip()  # ty:ignore[unresolved-attribute]
    return normalized if normalized != "" else None


def _resolve_manager_id_for_create(
    payload: "SignupRequestCreate", current_user: dict
) -> str | None:
    creator_role = current_user["account_type"]
    if creator_role == "rpm":
        if payload.account_type == "admin":
            raise HTTPException(
                status_code=403,
                detail="RPM users cannot create admin accounts",
            )
        return current_user["id"]

    requested_manager_id = _normalize_optional_text(payload.manager_id)

    if payload.account_type != "lc" and requested_manager_id is not None:
        raise HTTPException(
            status_code=400,
            detail="manager_id can only be set for local coordinator accounts",
        )

    if requested_manager_id is None:
        return None

    manager_user = read_user(user_id=requested_manager_id)
    if manager_user is None:
        raise HTTPException(status_code=400, detail="manager_id user not found")
    if manager_user["account_type"] != "rpm":
        raise HTTPException(
            status_code=400,
            detail="manager_id must reference an rpm user",
        )

    return requested_manager_id


def _get_signup_user_or_404(*, user_id: str, current_user: dict) -> dict:
    signup_user = get_signup_user_for_manager(
        user_id=user_id,
        requester_id=current_user["id"],
        requester_role=current_user["account_type"],
    )
    if signup_user is None:
        raise HTTPException(status_code=404, detail="Signup user not found")
    return signup_user


class SignupRequestCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: str | None = None
    states: list[str]
    account_type: Literal["admin", "lc", "rpm"]
    manager_id: str | None = None


class SignupRequestItem(BaseModel):
    id: str
    first_name: str
    last_name: str | None = None
    email: str | None = None
    states: list[str]
    account_type: Literal["admin", "lc", "rpm"]
    is_registered: bool
    manager_id: str | None = None
    signup_code: str | None = None
    notes_text: str | None = None


class SignupRequestCreated(SignupRequestItem):
    signup_code: str


class SignupRequestUpdate(BaseModel):
    states: list[str] | None = None
    notes_text: str | None = None


class AdminGetUserItem(BaseModel):
    id: str
    username: str
    first_name: str
    account_type: Literal["admin", "rpm", "lc"]
    states: list[str]
    manager_id: str | None = None


class AdminPatchRequest(BaseModel):
    states: list[str] | None = None
    manager_id: str | None = None


def _to_admin_user_item(payload: dict) -> AdminGetUserItem:
    manager_id = payload.get("manager_id")
    if payload["account_type"] != "lc":
        manager_id = None

    return AdminGetUserItem(
        id=payload["id"],
        username=payload["username"],
        first_name=payload["first_name"],
        account_type=payload["account_type"],
        states=payload["placing_states"],
        manager_id=manager_id,
    )


@router.post(path="/register", response_model=SignupRequestCreated, status_code=201)
def create_rpm_signup_request(
    payload: SignupRequestCreate,
    current_user: dict = Depends(get_current_user),
) -> SignupRequestCreated:
    _require_rpm_or_admin(current_user=current_user)

    normalized_email = _normalize_optional_text(payload.email)
    manager_id = _resolve_manager_id_for_create(
        payload=payload, current_user=current_user
    )

    try:
        created = create_pending_signup_user(
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=normalized_email,
            states=payload.states,
            account_type=payload.account_type,
            manager_id=manager_id,
        )

        if normalized_email is not None:
            email_sent = send_signup_invitation_email(
                recipient_email=normalized_email,
                first_name=payload.first_name,
                last_name=payload.last_name,
                signup_code=created["signup_code"],
            )
            if email_sent is False:
                logger.warning(
                    "Signup user %s created, but invitation email was not sent",
                    created["id"],
                )

        return SignupRequestCreated(**created)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(path="/register/{user_id}/resend-invitation")
def resend_rpm_signup_invitation(
    user_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    _require_rpm_or_admin(current_user=current_user)

    signup_user = _get_signup_user_or_404(user_id=user_id, current_user=current_user)

    if signup_user["is_registered"]:
        raise HTTPException(
            status_code=400,
            detail="Signup code has already been used",
        )

    recipient_email = _normalize_optional_text(signup_user.get("email"))
    if recipient_email is None:
        raise HTTPException(
            status_code=400,
            detail="Signup user does not have an email address",
        )

    signup_code = _normalize_optional_text(signup_user.get("signup_code"))
    if signup_code is None:
        raise HTTPException(status_code=500, detail="Signup code is unavailable")

    email_sent = send_signup_invitation_email(
        recipient_email=recipient_email,
        first_name=signup_user["first_name"],
        last_name=signup_user.get("last_name") or "",
        signup_code=signup_code,
    )
    if email_sent is False:
        raise HTTPException(status_code=500, detail="Failed to send invitation email")

    return {"message": "Invitation email resent successfully"}


@router.get(path="/register", response_model=list[SignupRequestItem])
def get_rpm_signup_requests(
    current_user: dict = Depends(get_current_user),
) -> list[SignupRequestItem]:
    _require_rpm_or_admin(current_user=current_user)
    rows = list_signup_users_for_manager(
        requester_id=current_user["id"],
        requester_role=current_user["account_type"],
    )

    notes_map = get_user_notes_for_owner(
        owner_id=current_user["id"],
        notes_user_ids=[str(row["id"]) for row in rows],
    )

    payload: list[SignupRequestItem] = []
    for row in rows:
        item = dict(row)
        item["notes_text"] = notes_map.get(str(item["id"]))
        payload.append(SignupRequestItem(**item))
    return payload


@router.patch(path="/register/{user_id}", response_model=SignupRequestItem)
def update_rpm_signup_request(
    user_id: str,
    payload: SignupRequestUpdate,
    current_user: dict = Depends(get_current_user),
) -> SignupRequestItem:
    _require_rpm_or_admin(current_user=current_user)

    update_states = "states" in payload.model_fields_set
    update_notes = "notes_text" in payload.model_fields_set
    if update_states is False and update_notes is False:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    signup_user = _get_signup_user_or_404(user_id=user_id, current_user=current_user)

    if update_states:
        states_updated = update_user_placing_states_by_id(
            user_id=user_id,
            states=payload.states or [],
        )
        if states_updated is False:
            raise HTTPException(status_code=404, detail="Signup user not found")

    if update_notes:
        upsert_user_note(
            owner_id=current_user["id"],
            notes_user_id=user_id,
            note_text=payload.notes_text if payload.notes_text is not None else "",
        )

    signup_user = _get_signup_user_or_404(user_id=user_id, current_user=current_user)
    signup_user["notes_text"] = get_user_note(
        owner_id=current_user["id"],
        notes_user_id=user_id,
    )
    return SignupRequestItem(**signup_user)


@router.get(
    path="/admin_get",
    response_model=list[SignupRequestItem],
)
def admin_get(
    current_user: dict = Depends(get_current_user),
) -> list[SignupRequestItem]:
    _require_admin(current_user=current_user)
    users = list_all_users_with_states()

    notes_map = get_user_notes_for_owner(
        owner_id=current_user["id"],
        notes_user_ids=[str(user["id"]) for user in users],
    )

    payload: list[SignupRequestItem] = []
    for user in users:
        item = {
            "id": user["id"],
            "username": user["username"],
            "first_name": user["first_name"],
            "last_name": user.get("last_name"),
            "email": user.get("email"),
            "states": user.get("placing_states") or [],
            "account_type": user["account_type"],
            "manager_id": user.get("manager_id"),
            "is_registered": user["is_registered"],
            "signup_code": user.get("signup_code"),
        }
        item["notes_text"] = notes_map.get(str(item["id"]))
        payload.append(SignupRequestItem(**item))  # ty:ignore[invalid-argument-type]
    return payload


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
    update_manager_id = "manager_id" in payload.model_fields_set
    if update_states is False and update_manager_id is False:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    user = get_user_with_states_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if update_manager_id:
        normalized_manager_id = _normalize_optional_text(payload.manager_id)

        if user["account_type"] != "lc" and normalized_manager_id is not None:
            raise HTTPException(
                status_code=400,
                detail="manager_id can only be set for local coordinator accounts",
            )

        if normalized_manager_id is not None:
            manager_user = read_user(user_id=normalized_manager_id)
            if manager_user is None:
                raise HTTPException(status_code=400, detail="manager_id user not found")
            if manager_user["account_type"] != "rpm":
                raise HTTPException(
                    status_code=400,
                    detail="manager_id must reference an rpm user",
                )

        manager_updated = update_user_manager_id_by_id(
            user_id=user_id,
            manager_id=normalized_manager_id,
        )
        if manager_updated is False:
            raise HTTPException(status_code=404, detail="User not found")

    if update_states:
        states_updated = update_user_placing_states_by_id(
            user_id=user_id,
            states=payload.states or [],
        )
        if states_updated is False:
            raise HTTPException(status_code=404, detail="User not found")

    user = get_user_with_states_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_admin_user_item(payload=user)


@router.delete(path="/admin_delete/{user_id}")
def admin_delete(
    user_id: str, current_user: dict = Depends(get_current_user)
) -> dict[str, str]:
    _require_admin(current_user=current_user)

    user = get_user_with_states_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    deleted = delete_user_by_id(user_id=user_id)
    if deleted is False:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}
