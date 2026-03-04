from fastapi import APIRouter, Depends, Query
from models.student import BasicStudent, FullStudent
from repositories.students import get_favorites
from repositories.users import update_user
from routers.auth import get_current_user
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
        return [BasicStudent(**student.model_dump()) for student in results]
    except Exception:
        return []


@router.patch(path="/favorites")
def add_favorite(
    app_id: str = Query(default=...), current_user=Depends(dependency=get_current_user)
):
    favorites = []
    if current_user["favorites"]:
        favorites = json.loads(current_user["favorites"])
    if app_id not in favorites:
        favorites.append(app_id)
        update_user(username=current_user["username"], favorites=favorites)
    return {"message": "Favorite added"}


@router.delete(path="/favorites")
def remove_favorite(
    app_id: str = Query(default=...), current_user=Depends(dependency=get_current_user)
):
    favorites = []
    if current_user["favorites"]:
        favorites = json.loads(current_user["favorites"])
    if app_id in favorites:
        favorites.remove(app_id)
        update_user(username=current_user["username"], favorites=favorites)
    return {"message": "Favorite removed"}


@router.get("/states")
def get_states(current_user=Depends(dependency=get_current_user)):
    try:
        states = json.loads(current_user["placing_states"])
        return states
    except Exception:
        return []


@router.patch("/states")
def update_states(
    states_list: list[str], current_user=Depends(dependency=get_current_user)
):
    try:
        update_user(username=current_user["username"], placing_states=states_list)
    except Exception as e:
        return {"message": f"Error - {e}"}
