import json

from fastapi import APIRouter, Depends, Query

from repositories.student_placement_events import list_student_placement_events
from routers.auth import get_current_user

router: APIRouter = APIRouter(prefix="/news_feed", tags=["news_feed"])


@router.get(path="")
def get_news_feed(
    limit: int = Query(default=100, ge=1, le=500),
    name: str | None = Query(default=None),
    new_status: str | None = Query(default=None),
    show_only_favorites: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
    
) -> list[dict]:
    favorite_student_ids: list[int] | None = None
    if show_only_favorites:
        favorites = []
        if current_user["favorites"]:
            print(current_user['favorites'])
            try:
                favorites = json.loads(current_user["favorites"])
            except json.JSONDecodeError:
                favorites = []
        favorite_student_ids = []
        for value in favorites:
            try:
                favorite_student_ids.append(int(value))
            except (TypeError, ValueError):
                continue

    return list_student_placement_events(
        limit=limit,
        name=name,
        new_status=new_status,
        favorite_student_ids=favorite_student_ids,
    )
