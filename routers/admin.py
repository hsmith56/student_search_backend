from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from repositories.users import (
    delete_user_by_id,
    list_all_users,
    list_users_by_account_type,
    read_user,
    update_user_account_type_by_id,
)
from routers.auth import get_current_user

router: APIRouter = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(current_user: dict) -> None:
    if current_user["account_type"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")


class AdminUserItem(BaseModel):
    id: str
    username: str
    first_name: str
    account_type: Literal["admin", "director", "rpm", "lc"]


class AdminUserAccountTypePatchRequest(BaseModel):
    account_type: Literal["admin", "director", "rpm", "lc"]


@router.get(path="/users", response_model=list[AdminUserItem])
def get_users(current_user: dict = Depends(get_current_user)) -> list[AdminUserItem]:
    _require_admin(current_user=current_user)
    return [AdminUserItem(**item) for item in list_all_users()]


@router.patch(path="/users/{user_id}", response_model=AdminUserItem)
def patch_user_account_type(
    user_id: str,
    payload: AdminUserAccountTypePatchRequest,
    current_user: dict = Depends(get_current_user),
) -> AdminUserItem:
    _require_admin(current_user=current_user)
    updated = update_user_account_type_by_id(
        user_id=user_id, account_type=payload.account_type
    )
    if updated is False:
        raise HTTPException(status_code=404, detail="User not found")

    user = read_user(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return AdminUserItem(
        id=user["id"],
        username=user["username"],
        first_name=user["first_name"],
        account_type=user["account_type"],
    )


@router.delete(path="/users/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    _require_admin(current_user=current_user)
    deleted = delete_user_by_id(user_id=user_id)
    if deleted is False:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


@router.get(path="/get_rpms", response_model=list[dict[str, str]])
def get_rpms(current_user: dict = Depends(get_current_user)) -> list[dict[str, str]]:
    _require_admin(current_user=current_user)
    rpm_users = list_users_by_account_type(account_type="rpm")
    director_users = list_users_by_account_type(account_type="director")
    return [{item["id"]: item["name"]} for item in [*director_users, *rpm_users]]
