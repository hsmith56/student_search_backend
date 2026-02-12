from datetime import datetime

import pytz

from repositories.base import get_connection


def initialize_db() -> None:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        first_name TEXT NOT NULL,
        favorites TEXT,
        account_type TEXT NOT NULL DEFAULT 'lc' CHECK (account_type IN ('admin', 'rpm', 'lc')),
        "Placing State" TEXT
    )
    """
    )



    cursor.execute(
        """
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
    """
    )

    cursor.execute(
        """
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
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS admin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        last_refresh_date TIMESTAMP,
        auth_code TEXT NOT NULL
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS feedback( 
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        first_name TEXT NOT NULL,
        comment TEXT NOT NULL,
        comment_date TIMESTAMP
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS student_placement_events(
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        first_name TEXT,
        event_type TEXT NOT NULL,
        event_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        placement_state TEXT,
        coordinator_id INTEGER,
        manager_id INTEGER,
        status_from TEXT,
        status_to TEXT
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS placement_metrics(
        app_id INTEGER PRIMARY KEY,
        city TEXT,
        state TEXT,
        placementDate TEXT NOT NULL
    );
    """
    )

    cursor.execute("PRAGMA table_info(placement_metrics)")
    # placement_metrics_columns = [row[1] for row in cursor.fetchall()]
    # if "hostFamilyName" in placement_metrics_columns:
    #     cursor.execute("DROP TABLE IF EXISTS placement_metrics_migrated")
    #     cursor.execute(
    #         """
    #     CREATE TABLE placement_metrics_migrated(
    #         app_id INTEGER PRIMARY KEY,
    #         city TEXT,
    #         state TEXT,
    #         placementDate TEXT NOT NULL
    #     );
    #     """
    #     )
    #     cursor.execute(
    #         """
    #     INSERT OR REPLACE INTO placement_metrics_migrated (app_id, city, state, placementDate)
    #     SELECT app_id, city, state, placementDate
    #     FROM placement_metrics
    #     WHERE placementDate IS NOT NULL
    #     """
    #     )
    #     cursor.execute("DROP TABLE placement_metrics")
    #     cursor.execute(
    #         "ALTER TABLE placement_metrics_migrated RENAME TO placement_metrics"
    #     )

    cursor.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_student_placement_events_student_time
    ON student_placement_events(student_id, event_at DESC);
    """
    )

    cursor.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_student_placement_events_type
    ON student_placement_events(event_type);
    """
    )

    cursor.execute("PRAGMA table_info(feedback)")
    feedback_columns = [row[1] for row in cursor.fetchall()]
    if "username" not in feedback_columns:
        cursor.execute(
            """
        ALTER TABLE feedback
        ADD COLUMN username TEXT DEFAULT ''
        """
        )

    cursor.execute("PRAGMA table_info(student_placement_events)")
    student_placement_event_columns = [row[1] for row in cursor.fetchall()]
    if "first_name" not in student_placement_event_columns:
        cursor.execute(
            """
        ALTER TABLE student_placement_events
        ADD COLUMN first_name TEXT
        """
        )

    cursor.execute("PRAGMA table_info(users)")
    user_columns = [row[1] for row in cursor.fetchall()]
    if "account_type" not in user_columns:
        cursor.execute(
            """
        ALTER TABLE users
        ADD COLUMN account_type TEXT NOT NULL DEFAULT 'lc' CHECK (account_type IN ('admin', 'rpm', 'lc'))
        """
        )
    if "Placing State" not in user_columns:
        cursor.execute(
            """
        ALTER TABLE users
        ADD COLUMN "Placing State" TEXT
        """
        )

    cursor.execute(
        """
    UPDATE users
    SET account_type = 'lc'
    WHERE account_type IS NULL
      OR account_type NOT IN ('admin', 'rpm', 'lc')
    """
    )

    connection.commit()
    connection.close()


def get_hashed_auth() -> str:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""SELECT auth_code FROM admin;""")
    auth_code = cursor.fetchone()
    connection.close()
    return auth_code[0]


def update_time() -> None:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM admin")

    now_time = datetime.now(pytz.timezone("US/Eastern"))

    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO admin (last_refresh_date, auth_code) VALUES (?, ?)",
            (now_time, "initial_code"),
        )

    cursor.execute(
        "UPDATE admin SET last_refresh_date = ? WHERE id = (SELECT id FROM admin LIMIT 1)",
        (now_time,),
    )
    connection.commit()
    connection.close()


def get_last_update_time() -> str:
    connection = get_connection(detect_types=True)
    cursor = connection.cursor()
    cursor.execute("SELECT last_refresh_date FROM admin")
    last_refresh_time: datetime = cursor.fetchone()[0]
    connection.commit()
    connection.close()

    return last_refresh_time.strftime("%b %d %H:%M EST")
