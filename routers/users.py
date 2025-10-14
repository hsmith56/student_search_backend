from fastapi import APIRouter, Depends, Query
from models.student import BasicStudent
from routers.students import STUDENTS
from routers.auth import get_current_user
from utils import db
import json

router = APIRouter(prefix="/user", tags=["user"])

@router.get("/", response_model=dict)
def get_user(current_user=Depends(get_current_user)):
    """Return the current logged-in user's info (from DB)."""
    user = {key: current_user[key] for key in current_user.keys()}
    return user

@router.get("/favorites")
def get_user_favorites(current_user=Depends(get_current_user)):
    """Return the favorites list for the current user."""
    favorites = []
    if current_user["favorites"]:
        try:
            favorites = json.loads(current_user["favorites"])
        except json.JSONDecodeError:
            pass

    print(favorites)
    return [
        BasicStudent(**student.model_dump())
        for student in STUDENTS
        if str(student.pax_id) in favorites
    ]

@router.patch("/favorites")
def add_favorite(pax_id: str = Query(...), current_user=Depends(get_current_user)):
    favorites = []
    if current_user["favorites"]:
        favorites = json.loads(current_user["favorites"])
    if pax_id not in favorites:
        favorites.append(pax_id)
        db.update_user(current_user["username"], favorites=favorites)
    return {"message": "Favorite added"}

@router.delete("/favorites")
def remove_favorite(pax_id: str = Query(...), current_user=Depends(get_current_user)):
    favorites = []
    if current_user["favorites"]:
        favorites = json.loads(current_user["favorites"])
    if pax_id in favorites:
        favorites.remove(pax_id)
        db.update_user(current_user["username"], favorites=favorites)
    return {"message": "Favorite removed"}
