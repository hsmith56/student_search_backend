from fastapi import APIRouter, Depends, Query

from models.search_filters import SearchFilters
from routers.students import ItemQueryParams, run_student_search

router: APIRouter = APIRouter(tags=["students"])


@router.post(path="/guest_search")
def guest_search(
    filters: SearchFilters,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=21, ge=1, le=100),
    params: ItemQueryParams = Depends(),
):
    return run_student_search(
        filters=filters, page=page, page_size=page_size, params=params
    )
