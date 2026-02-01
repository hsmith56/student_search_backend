from utils.beacon_refresh_stage2 import fill_out_student, run_stage_2_multi_threaded
from utils.beacon_refresh_stage1 import get_updates_from_beacon
from utils.db import get_all_full_students, get_full_student_by_id
import json
from enum import Enum
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from models.search_filters import SearchFilters
from models.student import BasicStudent, FullStudent
from utils import db
from utils.search_filters import filter_students

router: APIRouter = APIRouter(prefix="/students", tags=["students"])


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


@router.post(path="/search")
def search(
    filters: SearchFilters,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=21, ge=1, le=100),
    params: ItemQueryParams = Depends(),
):
    print(filters)

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


@router.get(path="/update_db")
def update_student_db() -> None:
    students_needing_stage_2 = get_updates_from_beacon()
    if len(students_needing_stage_2) != 0:
        run_stage_2_multi_threaded(students_needing_stage_2)
        # for student in students_needing_stage_2:
        #     fill_out_student(student)
    
    db.update_time()
    apply_filters.cache_clear()


db.update_time()