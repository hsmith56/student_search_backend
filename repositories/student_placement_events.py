import sqlite3
from datetime import datetime

import pytz

from repositories.base import get_connection


def _get_student_first_name(student_id: int) -> str | None:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT paxNameFirst
    FROM student_basic_overview
    WHERE applicationId = ?
    LIMIT 1
    """,
        (student_id,),
    )
    row = cursor.fetchone()
    connection.close()
    return str(row[0]) if row and row[0] not in (None, "") else None


def create_student_placement_event(
    student_id: int,
    event_type: str,
    first_name: str | None = None,
    placement_state: str | None = None,
    coordinator_id: int | None = None,
    manager_id: int | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    event_at: str | None = None,
) -> int:
    if event_at is None:
        event_at = datetime.now(pytz.timezone("US/Eastern")).isoformat()
    if first_name in (None, ""):
        first_name = _get_student_first_name(student_id)

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    INSERT INTO student_placement_events (
        student_id,
        first_name,
        event_type,
        event_at,
        placement_state,
        coordinator_id,
        manager_id,
        status_from,
        status_to
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            student_id,
            first_name,
            event_type,
            event_at,
            placement_state,
            coordinator_id,
            manager_id,
            status_from,
            status_to,
        ),
    )
    event_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return int(event_id)  # ty:ignore[invalid-argument-type]


def create_unassigned_to_allocated_event(
    student_id: int,
    first_name: str | None = None,
    coordinator_id: int | None = None,
    manager_id: int | None = None,
    event_at: str | None = None,
) -> int:
    return create_student_placement_event(
        student_id=student_id,
        first_name=first_name,
        event_type="status_changed",
        placement_state="Allocated",
        coordinator_id=coordinator_id,
        manager_id=manager_id,
        status_from="Unassigned",
        status_to="Allocated",
        event_at=event_at,
    )


def clear_student_placement_events() -> int:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM student_placement_events")
    existing_count = cursor.fetchone()
    rows_to_delete = int(existing_count[0]) if existing_count is not None else 0
    cursor.execute("DELETE FROM student_placement_events")
    try:
        cursor.execute(
            "DELETE FROM sqlite_sequence WHERE name = ?",
            ("student_placement_events",),
        )
    except sqlite3.OperationalError:
        # sqlite_sequence may not exist yet if AUTOINCREMENT has never been used.
        pass
    connection.commit()
    connection.close()
    return rows_to_delete


def list_student_placement_events(
    *,
    student_id: int | None = None,
    limit: int = 100,
    name: str | None = None,
    new_status: str | None = None,
    favorite_student_ids: list[int] | None = None,
) -> list[dict]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    where_clauses: list[str] = []
    values: list[object] = []

    if student_id is not None:
        where_clauses.append("student_id = ?")
        values.append(student_id)
    if name is not None and name.strip() != "":
        where_clauses.append("LOWER(COALESCE(first_name, '')) LIKE LOWER(?)")
        values.append(f"%{name.strip()}%")
    if new_status is not None and new_status.strip() != "":
        normalized_status = new_status.strip().lower()
        if normalized_status == "placed":
            where_clauses.append("LOWER(COALESCE(status_to, '')) LIKE ?")
            values.append("place%")
        else:
            where_clauses.append("LOWER(COALESCE(status_to, '')) = ?")
            values.append(normalized_status)
    if favorite_student_ids is not None:
        if len(favorite_student_ids) == 0:
            connection.close()
            return []
        placeholders = ",".join("?" for _ in favorite_student_ids)
        where_clauses.append(f"student_id IN ({placeholders})")
        values.extend(favorite_student_ids)

    query = """
    SELECT event_id, student_id, first_name, event_type, event_at, placement_state, coordinator_id, manager_id, status_from, status_to
    FROM student_placement_events
    """
    if where_clauses:
        query += "\nWHERE " + "\n  AND ".join(where_clauses)
    query += "\nORDER BY event_at DESC, event_id DESC\nLIMIT ?"
    values.append(limit)

    cursor.execute(query, tuple(values))

    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def get_latest_placement_event_id() -> int:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COALESCE(MAX(event_id), 0) FROM student_placement_events")
    latest = cursor.fetchone()
    connection.close()
    return int(latest[0]) if latest is not None else 0


def list_unassigned_to_allocated_events_after(
    after_event_id: int, limit: int = 100
) -> list[dict]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT event_id, student_id, first_name, event_type, event_at, placement_state, coordinator_id, manager_id, status_from, status_to
    FROM student_placement_events
    WHERE event_id > ?
      AND LOWER(COALESCE(status_from, '')) = LOWER(?)
      AND LOWER(COALESCE(status_to, '')) = LOWER(?)
    ORDER BY event_id ASC
    LIMIT ?
    """,
        (after_event_id, "Unassigned", "Allocated", limit),
    )
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]
