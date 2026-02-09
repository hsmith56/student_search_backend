import itertools
import json
import logging
import sqlite3
from typing import Any

from models.student import FullStudent
from repositories.base import get_connection
from utils.common_utils import _full_student_dict

logger = logging.getLogger(__name__)


def add_student_basic_overview(student) -> None:
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
        INSERT INTO student_basic_overview (id, usaHsId, applicationId, participantId, agencyId, placementStatusId, placementStatusName, paxNameLast, paxNameFirst, paxGender)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                student["id"],
                student["usaHsId"],
                student["applicationId"],
                student["participantId"],
                student["agencyId"],
                student["placementStatusId"],
                student["placementStatusName"],
                student["paxNameLast"],
                student["paxNameFirst"],
                student["paxGender"],
            ),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        logger.warning("add_student_basic_overview skipped: student already exists")
    finally:
        connection.close()


def update_student_status_basic_overview(app_id: int, placement_status: str) -> None:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE student_basic_overview SET placementStatusName = ? WHERE applicationId = ?
    """,
        (placement_status, app_id),
    )
    connection.commit()
    connection.close()


def update_student_status_full(app_id: int, placement_status: str, usahs_id: str) -> None:
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            if usahs_id:
                cursor.execute(
                    """
                    UPDATE student_full_view
                    SET placement_status = ?, 
                        usahsid = ?
                    WHERE app_id = ?
                    """,
                    (placement_status, usahs_id, app_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE student_full_view
                    SET placement_status = ?
                    WHERE app_id = ?
                    """,
                    (placement_status, app_id),
                )
            connection.commit()

    except Exception as e:
        logger.warning(f"Student - {app_id}: {e}")
    connection.close()



def query_full_students(query_param: str, query_val: str):
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    cursor.execute(
        f"""
    SELECT id FROM student_full_view WHERE {query_param} Like ?
    """,
        (query_val,),
    )
    students = cursor.fetchall()
    connection.close()
    students = list(itertools.chain.from_iterable(students))
    return students


def does_student_exist_basic_overview(student_app_id) -> tuple[int | None, str]:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
    SELECT applicationId, placementStatusName FROM student_basic_overview WHERE applicationId = ?
    """,
        (student_app_id,),
    )
    student = cursor.fetchone()
    connection.close()

    if student is None:
        return None, ""

    return student[0], student[1]


def get_countries() -> list[str]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    cursor.execute("SELECT DISTINCT country FROM student_full_view")

    countries = cursor.fetchall()
    connection.close()
    countries = list(itertools.chain.from_iterable(countries))
    return countries


def read_students() -> list[dict[str, Any]]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    cursor.execute(
        """
    SELECT id, usaHsId, applicationId, participantId, agencyId, placementStatusId, placementStatusName, paxNameLast, paxNameFirst, paxGender FROM student_basic_overview
    """
    )
    students = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return students


def delete_student(app_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    DELETE FROM simple_students WHERE app_id = ?
    """,
        (app_id,),
    )
    connection.commit()
    connection.close()


def to_json(value):
    if value is None:
        return None
    return json.dumps(list(value) if isinstance(value, set) else value)


def from_json(value, default):
    if value is None:
        return default
    return json.loads(value)


def bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def int_to_bool(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(value)


def insert_full_student(student):
    sql = """
    INSERT OR IGNORE INTO student_full_view (
        id, first_name, app_id, pax_id, country, gpa, english_score,
        applying_to_grade, usahsid, program_type, adjusted_age,
        selected_interests, urban_request, placement_status, gender_desc,
        current_grade, status, states, early_placement, single_placement,
        double_placement, free_text_interests, family_description,
        favorite_subjects, photo_comments, religion, allergy_comments,
        dietary_restrictions, religious_frequency, intro_message,
        message_to_host_family, message_from_natural_family, media_link,
        health_comments, live_with_pets, local_coordinator
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    student = _full_student_dict(student)

    values = (
        student.id,
        student.first_name,
        student.app_id,
        student.pax_id,
        student.country,
        student.gpa,
        student.english_score,
        student.applying_to_grade,
        student.usahsid,
        student.program_type,
        student.adjusted_age,
        to_json(student.selected_interests),
        student.urban_request,
        student.placement_status,
        student.gender_desc,
        student.current_grade,
        student.status,
        to_json(student.states),
        bool_to_int(student.early_placement),
        bool_to_int(student.single_placement),
        bool_to_int(student.double_placement),
        to_json(student.free_text_interests),
        student.family_description,
        student.favorite_subjects,
        student.photo_comments,
        student.religion,
        student.allergy_comments,
        student.dietary_restrictions,
        student.religious_frequency,
        student.intro_message,
        student.message_to_host_family,
        student.message_from_natural_family,
        student.media_link,
        to_json(student.health_comments),
        bool_to_int(student.live_with_pets),
        student.local_coordinator,
    )

    connection = get_connection(detect_types=True)
    cursor = connection.cursor()
    cursor.execute(sql, values)

    connection.commit()
    connection.close()


def row_to_student(row) -> FullStudent:
    data = dict(row)
    return FullStudent(
        id=data["id"],
        first_name=data["first_name"],
        app_id=data["app_id"],
        pax_id=data["pax_id"],
        country=data["country"],
        gpa=data["gpa"],
        english_score=data["english_score"],
        applying_to_grade=data["applying_to_grade"],
        usahsid=data["usahsid"],
        program_type=data["program_type"],
        adjusted_age=data["adjusted_age"],
        selected_interests=from_json(data["selected_interests"], []),
        urban_request=data["urban_request"],
        placement_status=data["placement_status"],
        gender_desc=data["gender_desc"],
        current_grade=data["current_grade"],
        status=data["status"],
        states=set(from_json(data["states"], [])),
        early_placement=int_to_bool(data["early_placement"]),
        single_placement=int_to_bool(data["single_placement"]),  # ty:ignore[invalid-argument-type]
        double_placement=int_to_bool(data["double_placement"]),  # ty:ignore[invalid-argument-type]
        free_text_interests=from_json(data["free_text_interests"], []),
        family_description=data["family_description"],
        favorite_subjects=data["favorite_subjects"],
        photo_comments=data["photo_comments"],
        religion=data["religion"],
        allergy_comments=data["allergy_comments"],
        dietary_restrictions=data["dietary_restrictions"],
        religious_frequency=data["religious_frequency"],
        intro_message=data["intro_message"],
        message_to_host_family=data["message_to_host_family"],
        message_from_natural_family=data["message_from_natural_family"],
        media_link=data["media_link"],
        health_comments=from_json(data["health_comments"], []),
        live_with_pets=int_to_bool(data["live_with_pets"]),
        local_coordinator=data["local_coordinator"],
    )


def get_all_full_students() -> list[FullStudent]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM student_full_view")
    list_of_all_students = [row_to_student(row) for row in cursor.fetchall()]
    connection.close()
    return list_of_all_students


def get_full_student_by_id(student_app_id) -> FullStudent | None:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    cursor.execute(
        """SELECT * FROM student_full_view WHERE app_id = ?""", (student_app_id,)
    )
    student = cursor.fetchone()
    connection.close()
    if student is not None:
        return row_to_student(student)
    return None


def get_favorites(favorites_list: list[int]) -> list[FullStudent]:
    if len(favorites_list) == 0:
        return []

    favorites_list = [int(x) for x in favorites_list]
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    placeholders = ",".join("?" for _ in favorites_list)
    cmd_str = f"""SELECT * FROM student_full_view WHERE pax_id IN ({placeholders})"""
    cursor.execute(cmd_str, favorites_list)
    list_of_all_students = [row_to_student(row) for row in cursor.fetchall()]
    connection.close()

    return list_of_all_students
