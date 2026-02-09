import hashlib
import json
import logging
import sqlite3
import uuid

from repositories.base import get_connection

logger = logging.getLogger(__name__)


def create_user(username, password, first_name, favorites=None) -> None:
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    user_id = str(uuid.uuid4())
    favorites_str = None
    if favorites is not None and isinstance(favorites, list):
        favorites_str = json.dumps(favorites)

    connection = get_connection()
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


def update_user(username: str, first_name: str = "", favorites=None) -> None:
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
