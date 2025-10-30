from fastapi import APIRouter
from utils.db import query_students, get_countries, get_last_update_time

router = APIRouter(prefix="/misc", tags=["misc"])


@router.get("/available_now")
def get_available_student_count():
    # return len([x for x in STUDENTS if "allocated" in x.status.lower()])
    allocated_students = query_students("placement_status", "allocated")
    return {len(allocated_students)}


@router.get("/unassigned_now")
def get_unassigned_student_count():
    # return len([x for x in STUDENTS if "allocated" in x.status.lower()])
    return {len(query_students("placement_status", "unassigned"))}


@router.get("/placed")
def get_students_placed():
    placed = query_students("placement_status", "%place%")
    return {len(placed)}


@router.get("/countries")
def get_unique_countries():
    countries = get_countries()
    if isinstance(countries, list):
        return sorted(countries)
    return []

@router.get("/last_update_time")
def get_update_time():
    placed = get_last_update_time()
    return {placed}