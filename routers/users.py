from utils.db import get_favorites
from fastapi import APIRouter, Depends, Query
from models.student import BasicStudent, FullStudent
from routers.auth import get_current_user
from utils import db
import json
from enum import Enum
from pydantic import BaseModel

router: APIRouter = APIRouter(prefix="/user", tags=["user"])


class OrderBy(str, Enum):
    s_name = "first_name"
    s_id = "id"
    country = "country"
    gpa = "gpa"
    age = "adjusted_age"
    status = "placement_status"


class ItemQueryParams(BaseModel):
    order_by: OrderBy = OrderBy.age
    descending: bool = True


@router.get(path="/", response_model=dict)
def get_user(current_user=Depends(get_current_user)):
    """Return the current logged-in user's info (from DB)."""
    user = {key: current_user[key] for key in current_user.keys()}
    return user


@router.get(path="/favorites")
def get_user_favorites(
    current_user=Depends(dependency=get_current_user),
    params: ItemQueryParams = Depends(),
) -> list[BasicStudent]:
    """Return the favorites list for the current user."""
    favorites = []
    if current_user["favorites"]:
        try:
            favorites = json.loads(current_user["favorites"])
        except json.JSONDecodeError:
            return []

    try:
        results: list[FullStudent] = get_favorites(favorites)
        results = sorted(
            results,
            key=lambda x: x.__getattribute__(params.order_by),
            reverse=params.descending,
        )
        return [
            BasicStudent(**student.model_dump()) for student in results
        ]
    except Exception:
        return []


@router.patch(path="/favorites")
def add_favorite(
    pax_id: str = Query(default=...), current_user=Depends(dependency=get_current_user)
):
    favorites = []
    if current_user["favorites"]:
        favorites = json.loads(current_user["favorites"])
    if pax_id not in favorites:
        favorites.append(pax_id)
        db.update_user(username=current_user["username"], favorites=favorites)
    return {"message": "Favorite added"}


@router.delete(path="/favorites")
def remove_favorite(
    pax_id: str = Query(default=...), current_user=Depends(dependency=get_current_user)
):
    favorites = []
    if current_user["favorites"]:
        favorites = json.loads(current_user["favorites"])
    if pax_id in favorites:
        favorites.remove(pax_id)
        db.update_user(username=current_user["username"], favorites=favorites)
    return {"message": "Favorite removed"}
