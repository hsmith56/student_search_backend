from utils.common_utils import _full_student_dict
from models.student import FullStudent
import sqlite3

import uuid
import json
import hashlib
import itertools
from datetime import datetime
import pytz


# Database setup
def initialize_db() -> None:
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        first_name TEXT NOT NULL,
        favorites TEXT
    )
    """)



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_basic_overview( 
        id INTEGER PRIMARY KEY,
        usaHsId TEXT,
        applicationId INTEGER UNIQUE NOT NULL,
        participantId INTEGER UNIQUE NOT NULL,
        agencyId INTEGER,
        placementStatusId INTEGER NOT NULL,
        placementStatusName TEXT NOT NULL,
        paxNameLast TEXT,
        paxNameFirst TEXT,
        paxGender INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_full_view(
        id INTEGER PRIMARY KEY,
        first_name TEXT NOT NULL,
        app_id INTEGER UNIQUE NOT NULL,
        pax_id INTEGER UNIQUE NOT NULL,
        country TEXT NOT NULL,
        gpa TEXT NOT NULL,
        english_score TEXT NOT NULL,
        applying_to_grade INTEGER NOT NULL,
        usahsid TEXT NOT NULL,
        program_type TEXT NOT NULL,
        adjusted_age INTEGER NOT NULL,
        selected_interests TEXT, 
        urban_request TEXT,
        placement_status TEXT,
        gender_desc TEXT,
        current_grade INTEGER NOT NULL,
        status TEXT,
        states TEXT,
        early_placement BOOLEAN DEFAULT 0,
        single_placement BOOLEAN NOT NULL,
        double_placement BOOLEAN NOT NULL,
        free_text_interests TEXT,
        family_description TEXT,
        favorite_subjects TEXT,
        photo_comments TEXT,
        religion TEXT,
        allergy_comments TEXT,
        dietary_restrictions TEXT,
        religious_frequency INTEGER,
        intro_message TEXT,
        message_to_host_family TEXT,
        message_from_natural_family TEXT,
        media_link TEXT,
        health_comments TEXT,
        live_with_pets BOOLEAN,
        local_coordinator TEXT DEFAULT ""
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        last_refresh_date TIMESTAMP,
        auth_code TEXT NOT NULL
        );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback( 
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        comment TEXT NOT NULL,
        comment_date TIMESTAMP
    );
    """)

    connection.commit()
    connection.close()


# Create a new user
def create_user(username, password, first_name, favorites=None) -> None:
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    user_id = str(uuid.uuid4())
    if favorites is not None:
        if isinstance(favorites, list):
            favorites_str = json.dumps(favorites)

    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
        INSERT INTO users (id, username, hashed_password, first_name, favorites)
        VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, username, hashed_password, first_name, favorites_str),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        print("Username already exists.")
    finally:
        connection.close()


# Read user data
def read_user(username="", user_id=""):
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    if username != "":
        cursor.execute(
            """
        SELECT * FROM users WHERE username = ?
        """,
            (username,),
        )
        user = cursor.fetchone()
        connection.close()
    else:
        cursor.execute(
            """
        SELECT * FROM users WHERE id = ?
        """,
            (user_id,),
        )
        user = cursor.fetchone()
        connection.close()
    return user


# Update user data
def update_user(username: str, first_name: str = "", favorites=None) -> None:
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    if first_name != "":
        cursor.execute(
            """
        UPDATE users SET first_name = ? WHERE username = ?
        """,
            (first_name, username),
        )
    if favorites is not None:
        if isinstance(favorites, list):
            favorites_str = json.dumps(favorites)
            cursor.execute(
                """
            UPDATE users SET favorites = ? WHERE username = ?
            """,
                (favorites_str, username),
            )
    connection.commit()
    connection.close()


# Delete a user
def delete_user(username) -> None:
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    cursor.execute(
        """
    DELETE FROM users WHERE username = ?
    """,
        (username,),
    )
    connection.commit()
    connection.close()


def add_student_basic_overview(student) -> None:
    connection = sqlite3.connect("user_auth.db")
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
        print("student already exists.")
    finally:
        connection.close()


def update_student_status_basic_overview(app_id: int, placement_status: str) -> None:
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE student_basic_overview SET placementStatusName = ? WHERE applicationId = ?
    """,
        (placement_status, app_id),
    )
    connection.commit()
    connection.close()


def query_full_students(query_param: str, query_val: str):
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
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
    connection = sqlite3.connect("user_auth.db")
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
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("SELECT DISTINCT country FROM student_full_view")

    countries = cursor.fetchall()
    connection.close()
    countries = list(itertools.chain.from_iterable(countries))
    return countries


# Read student data


def read_students():
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
    SELECT id, usaHsId, applicationId, participantId, agencyId, placementStatusId, placementStatusName, paxNameLast, paxNameFirst, paxGender FROM student_basic_overview
    """)
    students = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return students


# Delete a student
def delete_student(app_id):
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    cursor.execute(
        """
    DELETE FROM simple_students WHERE app_id = ?
    """,
        (app_id,),
    )
    connection.commit()
    connection.close()


def get_hashed_auth() -> str:
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    cursor.execute("""SELECT auth_code FROM admin;""")
    auth_code = cursor.fetchone()
    connection.close()
    return auth_code[0]


def update_time():
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM admin")

    now_time = datetime.now(pytz.timezone("US/Eastern"))

    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO admin (last_refresh_date, auth_code) VALUES (?, ?)",
            (now_time, "initial_code"),
        )

    # --- Update the only entry in the table ---
    cursor.execute(
        "UPDATE admin SET last_refresh_date = ? WHERE id = (SELECT id FROM admin LIMIT 1)",
        (now_time,),
    )
    connection.commit()
    connection.close()


def get_last_update_time() -> str:
    connection = sqlite3.connect(
        "user_auth.db", detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    cursor = connection.cursor()
    cursor.execute("SELECT last_refresh_date FROM admin")
    last_refresh_time: datetime = cursor.fetchone()[0]
    connection.commit()
    connection.close()

    return last_refresh_time.strftime("%b %d %H:%M EST")


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

    connection = sqlite3.connect(
        "user_auth.db", detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    cursor = connection.cursor()
    cursor.execute(sql, values)

    connection.commit()
    connection.close()


def row_to_student(row: sqlite3.Row) -> FullStudent:
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
        single_placement=int_to_bool(data["single_placement"]),
        double_placement=int_to_bool(data["double_placement"]),
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
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM student_full_view")
    list_of_all_students = [row_to_student(row) for row in cursor.fetchall()]
    connection.close()
    return list_of_all_students


def get_full_student_by_id(student_app_id) -> FullStudent | None:
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
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
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    placeholders = ",".join("?" for _ in favorites_list)
    cmd_str = f"""SELECT * FROM student_full_view WHERE pax_id IN ({placeholders})"""
    cursor.execute(cmd_str, favorites_list)
    list_of_all_students = [row_to_student(row) for row in cursor.fetchall()]
    connection.close()

    return list_of_all_students


initialize_db()


# add_student("harrison",1432, pax_id=123, country="United States", program_type="10 month jan", adjusted_age=15, placement_status="accepted")
# delete_student(1432)

# cursor.execute('''
# CREATE TABLE IF NOT EXISTS full_students (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     first_name TEXT NOT NULL,
#     app_id INTEGER NOT NULL,
#     pax_id INTEGER NOT NULL,
#     country TEXT NOT NULL,
#     gpa TEXT NOT NULL,
#     english_score TEXT NOT NULL,
#     applying_to_grade INTEGER NOT NULL,
#     usahsid TEXT NOT NULL,
#     program_type TEXT NOT NULL,
#     adjusted_age INTEGER NOT NULL,
#     selected_interests TEXT,  -- Store as JSON string
#     urban_request TEXT,
#     placement_status TEXT,
#     gender_desc TEXT,
#     current_grade INTEGER NOT NULL,
#     status TEXT,
#     states TEXT,  -- Store as JSON string
#     early_placement BOOLEAN DEFAULT 0,
#     single_placement BOOLEAN NOT NULL,
#     double_placement BOOLEAN NOT NULL,
#     free_text_interests TEXT,  -- Store as JSON string
#     family_description TEXT,
#     favorite_subjects TEXT,
#     photo_comments TEXT,
#     religion TEXT,
#     allergy_comments TEXT,
#     dietary_restrictions TEXT,
#     religious_frequency INTEGER,
#     intro_message TEXT,
#     message_to_host_family TEXT,
#     message_from_natural_family TEXT,
#     media_link TEXT,
#     health_comments TEXT,  -- Store as JSON string
#     live_with_pets BOOLEAN,
#     local_coordinator TEXT DEFAULT ""
# )
# ''')
