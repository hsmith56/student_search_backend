import logging
import time
from datetime import datetime, timedelta

import pytz

from repositories.admin import get_last_update_datetime, update_time
from repositories.students import get_all_full_students, get_full_student_by_id
from utils.beacon_refresh_stage2 import run_stage_2_multi_threaded
from utils.beacon_refresh_stage1 import get_updates_from_beacon
from enum import Enum
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from models.search_filters import SearchFilters
from models.student import BasicStudent, FullStudent
from routers.auth import get_current_user
from utils.search_filters import filter_students

router: APIRouter = APIRouter(prefix="/students", tags=["students"])
logger = logging.getLogger(__name__)


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


@router.get(path="/full/{app_id}", response_model=FullStudent)
def get_full_student(app_id: int) -> FullStudent:
    student = get_full_student_by_id(app_id)
    if student is not None:
        return student
    raise HTTPException(status_code=404, detail="Student not found")


@lru_cache(maxsize=128)
def apply_filters(filters: SearchFilters) -> list[FullStudent]:
    return filter_students(students=get_all_full_students(), filters=filters)


def run_student_search(
    filters: SearchFilters,
    page: int,
    page_size: int,
    params: ItemQueryParams,
) -> dict[str, Any]:
    logger.debug("student search filters=%s", filters.model_dump())

    results: list[FullStudent] = apply_filters(filters)  # pyright: ignore[reportRedeclaration, reportAssignmentType]

    results: list[FullStudent] = sorted(  # pyright: ignore[reportRedeclaration]
        results,
        key=lambda x: x.__getattribute__(params.order_by),
        reverse=params.descending,
    )

    results: list[BasicStudent] = [BasicStudent(**x.model_dump()) for x in results]

    total: int = len(results)
    start: int = (page - 1) * page_size
    end: int = start + page_size
    paginated: list[BasicStudent] = results[start:end]

    return {
        "page": page,
        "page_size": page_size,
        "total_results": total,
        "total_pages": (total + page_size - 1) // page_size,
        "results": paginated,
    }


@router.post(path="/search")
def search(
    filters: SearchFilters,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=21, ge=1, le=100),
    params: ItemQueryParams = Depends(),
):
    return run_student_search(
        filters=filters, page=page, page_size=page_size, params=params
    )


@router.post(path="/update_db")
def update_student_db(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["account_type"] == "lc":
        raise HTTPException(status_code=401, detail="Unauthorized")

    last_update = get_last_update_datetime()
    if last_update is not None:
        eastern = pytz.timezone("US/Eastern")
        now = datetime.now(eastern)
        if last_update.tzinfo is None:
            last_update = eastern.localize(last_update)
        else:
            last_update = last_update.astimezone(eastern)
        if now - last_update < timedelta(hours=4):
            return {
                "message": "Student refresh skipped",
                "detail": "Last refresh was less than 4 hours ago",
            }

    start = time.perf_counter()
    students_needing_stage_2 = get_updates_from_beacon()
    processed = len(students_needing_stage_2)
    if len(students_needing_stage_2) != 0:
        run_stage_2_multi_threaded(students_needing_stage_2)

    end = time.perf_counter()

    update_time()
    apply_filters.cache_clear()
    return {"message": "Student refresh completed", "stage_2_processed": processed, "total_time": end-start}
