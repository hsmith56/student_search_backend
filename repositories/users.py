import hashlib
import json
import logging
import sqlite3
import uuid

from repositories.base import get_connection

logger = logging.getLogger(__name__)


def create_user(
    username,
    password,
    first_name,
    favorites=None,
    account_type: str = "lc",
    placing_states: list[str] | str | None = None,
) -> None:
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    user_id = str(uuid.uuid4())
    favorites_str = None
    if favorites is not None and isinstance(favorites, list):
        favorites_str = json.dumps(favorites)
    placing_states_str = placing_states
    if placing_states is not None and isinstance(placing_states, list):
        placing_states_str = json.dumps(placing_states)
    if account_type not in {"admin", "rpm", "lc"}:
        account_type = "lc"

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
            "placing_states"
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                username,
                hashed_password,
                first_name,
                favorites_str,
                account_type,
                placing_states_str,
            ),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        logger.warning("create_user skipped: username already exists")
    finally:
        connection.close()


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


def update_user(
    username: str,
    first_name: str = "",
    favorites=None,
    account_type: str | None = None,
    placing_states: str | None = None,
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
        if account_type not in {"admin", "rpm", "lc"}:
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
