from datetime import datetime

import pytz

from repositories.base import get_connection


def create_feedback(
    username: str,
    first_name: str,
    comment: str,
    comment_date: str | None = None,
) -> int:
    if comment_date is None:
        comment_date = datetime.now(pytz.timezone("US/Eastern")).isoformat()

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    INSERT INTO feedback (username, first_name, comment, comment_date)
    VALUES (?, ?, ?, ?)
    """,
        (username, first_name, comment, comment_date),
    )
    feedback_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return int(feedback_id)  # ty:ignore[invalid-argument-type]


def get_feedback(feedback_id: int):
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT id, username, first_name, comment, comment_date
    FROM feedback
    WHERE id = ?
    """,
        (feedback_id,),
    )
    feedback = cursor.fetchone()
    connection.close()
    return dict(feedback) if feedback else None


def list_feedback() -> list[dict]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT id, username, first_name, comment, comment_date
    FROM feedback
    ORDER BY id DESC
    """
    )
    feedback_rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in feedback_rows]


def update_feedback(
    feedback_id: int,
    username: str | None = None,
    first_name: str | None = None,
    comment: str | None = None,
) -> bool:
    updates = []
    values = []

    if username is not None:
        updates.append("username = ?")
        values.append(username)
    if first_name is not None:
        updates.append("first_name = ?")
        values.append(first_name)
    if comment is not None:
        updates.append("comment = ?")
        values.append(comment)

    updates.append("comment_date = ?")
    values.append(datetime.now(pytz.timezone("US/Eastern")).isoformat())

    values.append(feedback_id)
    set_clause = ", ".join(updates)

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        f"""
    UPDATE feedback
    SET {set_clause}
    WHERE id = ?
    """,
        tuple(values),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def delete_feedback(feedback_id: int) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    DELETE FROM feedback
    WHERE id = ?
    """,
        (feedback_id,),
    )
    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return deleted
