import sqlite3
import uuid
import json
import hashlib
import itertools
from datetime import datetime
import pytz


# Database setup
def initialize_db():
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
    CREATE TABLE IF NOT EXISTS simple_students( 
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        app_id INTEGER UNIQUE NOT NULL,
        pax_id INTEGER UNIQUE NOT NULL,
        country TEXT NOT NULL,
        program_type TEXT NOT NULL,
        adjusted_age INTEGER NOT NULL,
        placement_status TEXT
    )
    """)

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        last_refresh_date TIMESTAMP,
        auth_code TEXT NOT NULL
        );
    ''')

    connection.commit()
    connection.close()


# Create a new user
def create_user(username, password, first_name, favorites=None):
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
def update_user(username: str, first_name: str = "", favorites=None):
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
def delete_user(username):
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


def add_student(
    first_name: str,
    app_id: int,
    pax_id: int,
    country: str,
    program_type: str,
    adjusted_age: int,
    placement_status: str,
):
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
        INSERT INTO simple_students (first_name, app_id, pax_id, country, program_type, adjusted_age, placement_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                first_name,
                app_id,
                pax_id,
                country,
                program_type,
                adjusted_age,
                placement_status,
            ),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        print("student already exists.")
    finally:
        connection.close()


def update_student_status(app_id: int, placement_status: str):
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE simple_students SET placement_status = ? WHERE app_id = ?
    """,
        (placement_status, app_id),
    )
    connection.commit()
    connection.close()


def query_students(query_param: str, query_val: str):
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        f"""
    SELECT id FROM simple_students WHERE {query_param} Like ?
    """,
        (query_val,),
    )
    students = cursor.fetchall()
    connection.close()
    students = list(itertools.chain.from_iterable(students))
    return students

def does_student_exist(student_id):
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()

    cursor.execute(
        f"""
    SELECT app_id, placement_status FROM simple_students WHERE app_id = ?
    """,
        (student_id,),
    )
    student = cursor.fetchone()
    connection.close()

    if student is None:
        return None, None

    return student[0], student[1]


def get_countries():
    connection = sqlite3.connect("user_auth.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("SELECT DISTINCT country FROM simple_students")

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
    SELECT app_id FROM simple_students
    """)
    students = cursor.fetchall()
    connection.close()
    students = list(itertools.chain.from_iterable(students))
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
    cursor.execute("""SELECT auth_code FROM admin;"""
    )
    auth_code = cursor.fetchone()
    connection.close()
    return auth_code[0]

def update_time():
    connection = sqlite3.connect("user_auth.db")
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM admin")

    now_time= datetime.now(pytz.timezone('US/Eastern'))

    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO admin (last_refresh_date, auth_code) VALUES (?, ?)", 
                    (now_time, "initial_code"))

    # --- Update the only entry in the table ---
    cursor.execute("UPDATE admin SET last_refresh_date = ? WHERE id = (SELECT id FROM admin LIMIT 1)",
                (now_time,))
    connection.commit()
    connection.close()

def get_last_update_time():
    connection = sqlite3.connect("user_auth.db", detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    cursor = connection.cursor()
    cursor.execute("SELECT last_refresh_date FROM admin")
    last_refresh_time: datetime = cursor.fetchone()[0]
    connection.commit()
    connection.close()

    return last_refresh_time.strftime("%b %d %H:%M EST")



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
