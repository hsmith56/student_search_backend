from datetime import datetime

import pytz

from repositories.base import get_connection


def create_student_placement_event(
    student_id: int,
    event_type: str,
    placement_state: str | None = None,
    coordinator_id: int | None = None,
    manager_id: int | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    event_at: str | None = None,
) -> int:
    if event_at is None:
        event_at = datetime.now(pytz.timezone("US/Eastern")).isoformat()

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    INSERT INTO student_placement_events (
        student_id,
        event_type,
        event_at,
        placement_state,
        coordinator_id,
        manager_id,
        status_from,
        status_to
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            student_id,
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


def list_student_placement_events(
    *, student_id: int | None = None, limit: int = 100
) -> list[dict]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    if student_id is None:
        cursor.execute(
            """
        SELECT event_id, student_id, event_type, event_at, placement_state, coordinator_id, manager_id, status_from, status_to
        FROM student_placement_events
        ORDER BY event_at DESC, event_id DESC
        LIMIT ?
        """,
            (limit,),
        )
    else:
        cursor.execute(
            """
        SELECT event_id, student_id, event_type, event_at, placement_state, coordinator_id, manager_id, status_from, status_to
        FROM student_placement_events
        WHERE student_id = ?
        ORDER BY event_at DESC, event_id DESC
        LIMIT ?
        """,
            (student_id, limit),
        )

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
    SELECT event_id, student_id, event_type, event_at, placement_state, coordinator_id, manager_id, status_from, status_to
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
