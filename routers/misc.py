from fastapi import APIRouter
from utils.db import query_students

router = APIRouter(prefix="/misc", tags=["misc"])

@router.get("/available_now")
def get_available_student_count():
    # return len([x for x in STUDENTS if "allocated" in x.status.lower()])
    blah = query_students("placement_status","allocated")
    print(blah)
    return {len(blah)}


@router.get("/unassigned_now")
def get_unassigned_student_count():
    # return len([x for x in STUDENTS if "allocated" in x.status.lower()])
    return {len(query_students("placement_status","unassigned"))}

@router.get("/placed")
def get_students_placed():
    placed = query_students("placement_status","%place%")
    return {len(placed)}
