from fastapi import APIRouter
from utils.db import query_students, get_countries, get_last_update_time

router: APIRouter = APIRouter(prefix="/misc", tags=["misc"])


@router.get(path="/available_now")
def get_available_student_count():
    # return len([x for x in STUDENTS if "allocated" in x.status.lower()])
    allocated_students = query_students(query_param="placement_status", query_val="allocated")
    return {len(allocated_students)}


@router.get(path="/unassigned_now")
def get_unassigned_student_count():
    # return len([x for x in STUDENTS if "allocated" in x.status.lower()])
    return {len(query_students(query_param="placement_status", query_val="unassigned"))}


@router.get(path="/placed")
def get_students_placed():
    placed = query_students(query_param="placement_status", query_val="%place%")
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
