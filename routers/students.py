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


def _full_student_dict(student: dict) -> FullStudent:
    # helper func to avoid having to retype this entire section each time
    return FullStudent(
        first_name=student["namefirst"],
        app_id=student["applicationid"],
        pax_id=student["participantid"],
        country=student["residenceCountry"],
        gpa=student["schoolInfoGPA"],
        english_score=student["englishTestScore"],
        applying_to_grade=student["gradeApplyingTo"],
        usahsid=student["usahsId"],
        program_type=student["program_type"]
        .replace("High School USA ", "")
        .replace("Exchange", "")
        .replace("2026 ", "")
        .strip(),
        adjusted_age=student["adjusted_age"],
        gender_desc=student["genderdescription"],
        id=student["student_id"],
        current_grade=student["currentGradeLevel"],
        status=student["statussystemname"],
        states=student["states"],
        early_placement=student["early_placement"],
        urban_request=student["urban"],
        single_placement=student["single_placement"],
        double_placement=student["double_placement"],
        free_text_interests=student["interests"]["free_text"],
        family_description=student["interests"]["family_description"],
        favorite_subjects=student["interests"]["favorite_subject"],
        selected_interests=student["interests"]["selectables"],
        photo_comments=student["photo_comments"],
        religion=student["religion"],
        allergy_comments=student["allergies_comment"],
        dietary_restrictions=student["diet_comment"],
        religious_frequency=student["religiousFrequency"],
        intro_message=student["messages"][0],
        message_to_host_family=student["messages"][1],
        message_from_natural_family=student["messages"][2],
        media_link=student.get("media_link", ""),
        health_comments=student["health_comments"],
        live_with_pets=student["can_live_w_pets"],
        placement_status=student["placementStatusName"].title(),
    )


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "student_extra_info.json"
with open(DATA_PATH) as f:
    student_data = json.load(f)
    STUDENTS: list[FullStudent] = [
        _full_student_dict(s)
        for s in student_data
        if s.get("namefirst").lower() != "test"
        and s.get("statussystemname").lower() != "canceled"
    ]
    PLACED_STUDENTS: list[FullStudent] = [
        x
        for x in STUDENTS
        if x.placement_status.lower() != "allocated"
        and x.placement_status.lower() != "unassigned"
    ]
    PLACEABLE_STUDENTS: list[FullStudent] = [
        x
        for x in STUDENTS
        if x.placement_status.lower() == "allocated"
        or x.placement_status.lower() == "unassigned"
    ]

_existing_students = db.read_students()

for student in STUDENTS:
    if student.app_id not in _existing_students:
        db.add_student(
            first_name=student.first_name,
            app_id=student.app_id,
            pax_id=student.pax_id,
            country=student.country,
            program_type=student.program_type,
            adjusted_age=student.adjusted_age,
            placement_status=student.placement_status,
        )
    else:
        try:
            db.update_student_status(
                app_id=student.app_id, placement_status=student.placement_status
            )
        except Exception as e:
            print(e)

current_s_ids = {s.app_id for s in STUDENTS}
for student in _existing_students:
    if student not in current_s_ids:
        db.delete_student(student)


@router.get(path="/")
def list_students():
    return {"First Student": PLACEABLE_STUDENTS[0:10]}


@router.get(path="/basic/{app_id}", response_model=BasicStudent)
def get_basic_student(app_id: int) -> BasicStudent:
    for student in STUDENTS:
        if student.app_id == app_id:
            return BasicStudent(**student.model_dump())
    raise HTTPException(status_code=404, detail="Student not found")


@router.get(path="/full/{app_id}", response_model=FullStudent)
def get_full_student(app_id: int) -> FullStudent:
    ...
    for student in STUDENTS:
        if student.app_id == app_id:
            return student
    raise HTTPException(status_code=404, detail="Student not found")


@lru_cache(maxsize=128)
def apply_filters(filters: SearchFilters) -> list[FullStudent]:
    return filter_students(students=STUDENTS, filters=filters)


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
    apply_filters.cache_clear()
