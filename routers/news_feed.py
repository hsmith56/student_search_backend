from fastapi import APIRouter, Query

from repositories.student_placement_events import list_student_placement_events

router: APIRouter = APIRouter(prefix="/news_feed", tags=["news_feed"])


@router.get(path="")
def get_news_feed(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    return list_student_placement_events(limit=limit)
