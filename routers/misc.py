from fastapi import APIRouter
from repositories.admin import get_last_update_time
from repositories.students import get_countries, query_full_students

router: APIRouter = APIRouter(prefix="/misc", tags=["misc"])


@router.get(path="/available_now")
def get_available_student_count():
    allocated_students = query_full_students(
        query_param="placement_status", query_val="Allocated"
    )
    return {len(allocated_students)}


@router.get(path="/unassigned_now")
def get_unassigned_student_count():
    return {
        len(query_full_students(query_param="placement_status", query_val="unassigned"))
    }


@router.get(path="/placed")
def get_students_placed():
    placed = query_full_students(query_param="placement_status", query_val="%place%")
    return {len(placed)}


@router.get(path="/countries")
def get_unique_countries():
    countries = get_countries()
    if isinstance(countries, list):
        return sorted(countries)
    return []


@router.get(path="/last_update_time")
def get_update_time():
    placed = get_last_update_time()
    return {placed}
