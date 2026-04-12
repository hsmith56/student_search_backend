import hashlib
import json
import logging
import secrets
import sqlite3
import string
import uuid

from repositories.base import get_connection

logger = logging.getLogger(__name__)

_VALID_ACCOUNT_TYPES = {"admin", "rpm", "lc"}
_CODE_LETTERS = string.ascii_uppercase
_CODE_DIGITS = string.digits


def _normalize_account_type(account_type: str) -> str:
    normalized = account_type.strip().lower()
    if normalized not in _VALID_ACCOUNT_TYPES:
        raise ValueError("Invalid account_type")
    return normalized


def _normalize_signup_code(signup_code: str) -> str:
    return signup_code.strip().upper()


def _generate_signup_code(account_type: str) -> str:
    prefix_map = {
        "admin": "ADM",
        "rpm": "RPM",
        "lc": "LC",
    }
    prefix = prefix_map[account_type]
    letters = "".join(secrets.choice(_CODE_LETTERS) for _ in range(4))
    digits = "".join(secrets.choice(_CODE_DIGITS) for _ in range(4))
    return f"{prefix}-{letters}-{digits}"


def _parse_placing_states(placing_states_raw: str | None) -> list[str]:
    if not placing_states_raw:
        return []

    try:
        parsed = json.loads(placing_states_raw)
    except json.JSONDecodeError:
        return []

    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def _to_signup_user_dict(row: sqlite3.Row, note_text: str | None = None) -> dict:
    item = dict(row)
    return {
        "id": item["id"],
        "username": item["username"],
        "first_name": item["first_name"],
        "last_name": item.get("last_name"),
        "email": item.get("email"),
        "states": _parse_placing_states(item.get("placing_states")),  # ty:ignore[invalid-argument-type]
        "account_type": item["account_type"],
        "manager_id": item.get("manager_id"),
        "is_registered": bool(item.get("is_registered", 1)),
        "signup_code": item.get("signup_code"),
        "notes_text": note_text,
    }


def create_user(
    username,
    password,
    first_name,
    favorites=None,
    account_type: str = "lc",
    placing_states: list[str] | str | None = None,
    submitter_id: str | None = None,
    manager_id: str | None = None,
    email: str | None = None,
    last_name: str | None = None,
    signup_code: str | None = None,
    is_registered: bool = True,
) -> None:
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    user_id = str(uuid.uuid4())
    favorites_str = None
    if favorites is not None and isinstance(favorites, list):
        favorites_str = json.dumps(favorites)

    placing_states_str = placing_states
    if placing_states is not None and isinstance(placing_states, list):
        placing_states_str = json.dumps(placing_states)

    if account_type not in _VALID_ACCOUNT_TYPES:
        account_type = "lc"

    effective_manager_id = manager_id if manager_id is not None else submitter_id
    effective_submitter_id = submitter_id if submitter_id is not None else manager_id
    normalized_signup_code = (
        _normalize_signup_code(signup_code)
        if isinstance(signup_code, str) and signup_code.strip() != ""
        else None
    )

    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
        INSERT INTO users (
            id,
            username,
            hashed_password,
            first_name,
            favorites,
            account_type,
            "placing_states",
            email,
            last_name,
            manager_id,
            signup_code,
            is_registered,
            submitter_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                username,
                hashed_password,
                first_name,
                favorites_str,
                account_type,
                placing_states_str,
                email,
                last_name,
                effective_manager_id,
                normalized_signup_code,
                1 if is_registered else 0,
                effective_submitter_id,
            ),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        logger.warning("create_user skipped: username or signup code already exists")
    finally:
        connection.close()


def create_pending_signup_user(
    *,
    first_name: str,
    last_name: str,
    email: str | None,
    states: list[str],
    account_type: str,
    manager_id: str | None,
    max_attempts: int = 10,
) -> dict:
    normalized_type = _normalize_account_type(account_type)
    states_json = json.dumps([str(state) for state in states])

    for _ in range(max_attempts):
        user_id = str(uuid.uuid4())
        placeholder_username = str(uuid.uuid4())
        signup_code = _generate_signup_code(account_type=normalized_type)

        connection = get_connection(row_factory=True)
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
            INSERT INTO users (
                id,
                username,
                hashed_password,
                first_name,
                favorites,
                account_type,
                "placing_states",
                email,
                last_name,
                manager_id,
                signup_code,
                is_registered,
                submitter_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    user_id,
                    placeholder_username,
                    "_",
                    first_name,
                    None,
                    normalized_type,
                    states_json,
                    email,
                    last_name,
                    manager_id,
                    signup_code,
                    0,
                    manager_id,
                ),
            )
            connection.commit()

            cursor.execute(
                """
            SELECT id, username, first_name, last_name, email, account_type,
                   "placing_states", manager_id, signup_code, is_registered
            FROM users
            WHERE id = ?
            LIMIT 1
            """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Failed to load created signup user")
            return _to_signup_user_dict(row=row)
        except sqlite3.IntegrityError as exc:
            if "signup_code" in str(exc).lower() or "username" in str(exc).lower():
                continue
            raise
        finally:
            connection.close()

    raise RuntimeError("Failed to generate unique signup code")


def get_pending_user_by_signup_code(*, signup_code: str) -> dict | None:
    normalized_signup_code = _normalize_signup_code(signup_code)
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT *
    FROM users
    WHERE signup_code = ?
      AND is_registered = 0
    LIMIT 1
    """,
        (normalized_signup_code,),
    )
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    return dict(row)


def complete_signup_registration(
    *, user_id: str, username: str, password: str, first_name: str
) -> bool:
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE users
    SET username = ?,
        hashed_password = ?,
        first_name = ?,
        is_registered = 1
    WHERE id = ?
      AND is_registered = 0
    """,
        (username, hashed_password, first_name, user_id),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def list_signup_users_for_manager(
    *, requester_id: str, requester_role: str
) -> list[dict]:
    normalized_role = requester_role.strip().lower()
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    if normalized_role == "admin":
        cursor.execute(
            """
        SELECT id, username, first_name, last_name, email, account_type,
               "placing_states", manager_id, signup_code, is_registered
        FROM users
        ORDER BY rowid DESC
        """
        )
    else:
        cursor.execute(
            """
        SELECT id, username, first_name, last_name, email, account_type,
               "placing_states", manager_id, signup_code, is_registered
        FROM users
        WHERE manager_id = ?
        ORDER BY rowid DESC
        """,
            (requester_id,),
        )

    rows = cursor.fetchall()
    connection.close()
    return [_to_signup_user_dict(row=row) for row in rows]


def get_signup_user_for_manager(
    *, user_id: str, requester_id: str, requester_role: str
) -> dict | None:
    normalized_role = requester_role.strip().lower()
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    if normalized_role == "admin":
        cursor.execute(
            """
        SELECT id, username, first_name, last_name, email, account_type,
               "placing_states", manager_id, signup_code, is_registered
        FROM users
        WHERE id = ?
          AND signup_code IS NOT NULL
        LIMIT 1
        """,
            (user_id,),
        )
    else:
        cursor.execute(
            """
        SELECT id, username, first_name, last_name, email, account_type,
               "placing_states", manager_id, signup_code, is_registered
        FROM users
        WHERE id = ?
          AND manager_id = ?
          AND signup_code IS NOT NULL
        LIMIT 1
        """,
            (user_id, requester_id),
        )

    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    return _to_signup_user_dict(row=row)


def read_user(username="", user_id=""):
    connection = get_connection(row_factory=True)
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


def list_users_by_account_type(*, account_type: str) -> list[dict]:
    normalized_account_type = account_type.strip().lower()
    if normalized_account_type not in _VALID_ACCOUNT_TYPES:
        return []

    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT id, first_name
    FROM users
    WHERE account_type = ?
    ORDER BY first_name COLLATE NOCASE ASC, id ASC
    """,
        (normalized_account_type,),
    )
    rows = cursor.fetchall()
    connection.close()
    return [{"id": row["id"], "name": row["first_name"]} for row in rows]


def list_all_users() -> list[dict]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT id, username, first_name, account_type
    FROM users
    ORDER BY username COLLATE NOCASE ASC, id ASC
    """
    )
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def list_all_users_with_states() -> list[dict]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT id, username, first_name, last_name, email, account_type,
           "placing_states", manager_id, is_registered, signup_code
    FROM users
    ORDER BY username COLLATE NOCASE ASC, id ASC
    """
    )
    rows = cursor.fetchall()
    connection.close()

    users: list[dict] = []
    for row in rows:
        item = dict(row)
        users.append(
            {
                "id": item["id"],
                "username": item["username"],
                "first_name": item["first_name"],
                "last_name": item.get("last_name"),
                "email": item.get("email"),
                "account_type": item["account_type"],
                "placing_states": _parse_placing_states(item.get("placing_states")),
                "manager_id": item.get("manager_id"),
                "is_registered": bool(item.get("is_registered", 1)),
                "signup_code": item.get("signup_code"),
            }
        )
    return users


def get_user_with_states_by_id(*, user_id: str) -> dict | None:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT id, username, first_name, last_name, email, account_type,
           "placing_states", manager_id, is_registered, signup_code
    FROM users
    WHERE id = ?
    LIMIT 1
    """,
        (user_id,),
    )
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None

    item = dict(row)
    return {
        "id": item["id"],
        "username": item["username"],
        "first_name": item["first_name"],
        "last_name": item.get("last_name"),
        "email": item.get("email"),
        "account_type": item["account_type"],
        "placing_states": _parse_placing_states(item.get("placing_states")),
        "manager_id": item.get("manager_id"),
        "is_registered": bool(item.get("is_registered", 1)),
        "signup_code": item.get("signup_code"),
    }


def update_user_account_type_by_id(*, user_id: str, account_type: str) -> bool:
    normalized_account_type = account_type.strip().lower()
    if normalized_account_type not in _VALID_ACCOUNT_TYPES:
        raise ValueError("Invalid account_type")

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT 1
    FROM users
    WHERE id = ?
    LIMIT 1
    """,
        (user_id,),
    )
    if cursor.fetchone() is None:
        connection.close()
        return False

    cursor.execute(
        """
    UPDATE users
    SET account_type = ?
    WHERE id = ?
    """,
        (normalized_account_type, user_id),
    )
    connection.commit()
    connection.close()
    return True


def delete_user_by_id(*, user_id: str) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    DELETE FROM users
    WHERE id = ?
    """,
        (user_id,),
    )
    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return deleted


def update_user(
    username: str,
    first_name: str = "",
    favorites=None,
    account_type: str | None = None,
    placing_states: list[str] | None = None,
) -> None:
    connection = get_connection()
    cursor = connection.cursor()
    if first_name != "":
        cursor.execute(
            """
        UPDATE users SET first_name = ? WHERE username = ?
        """,
            (first_name, username),
        )
    if favorites is not None and isinstance(favorites, list):
        favorites_str = json.dumps(favorites)
        cursor.execute(
            """
        UPDATE users SET favorites = ? WHERE username = ?
        """,
            (favorites_str, username),
        )
    if account_type is not None:
        if account_type not in _VALID_ACCOUNT_TYPES:
            account_type = "lc"
        cursor.execute(
            """
        UPDATE users SET account_type = ? WHERE username = ?
        """,
            (account_type, username),
        )
    if placing_states is not None and isinstance(placing_states, list):
        placing_states_str = json.dumps(placing_states)
        cursor.execute(
            """
        UPDATE users SET "placing_states" = ? WHERE username = ?
        """,
            (placing_states_str, username),
        )
    connection.commit()
    connection.close()


def update_user_placing_states_by_id(*, user_id: str, states: list[str]) -> bool:
    serialized_states = json.dumps([str(state) for state in states])
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE users
    SET "placing_states" = ?
    WHERE id = ?
    """,
        (serialized_states, user_id),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def update_user_manager_id_by_id(*, user_id: str, manager_id: str | None) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE users
    SET manager_id = ?,
        submitter_id = ?
    WHERE id = ?
    """,
        (manager_id, manager_id, user_id),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def update_user_submitter_id_by_id(*, user_id: str, submitter_id: str | None) -> bool:
    return update_user_manager_id_by_id(user_id=user_id, manager_id=submitter_id)


def update_user_password_by_id(*, user_id: str, hashed_password: str) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE users
    SET hashed_password = ?
    WHERE id = ?
    """,
        (hashed_password, user_id),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def delete_user(username) -> None:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    DELETE FROM users WHERE username = ?
    """,
        (username,),
    )
    connection.commit()
    connection.close()
