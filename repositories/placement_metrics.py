from repositories.base import get_connection


def create_placement_metric(
    app_id: int,
    city: str | None,
    state: str | None,
    placement_date: str,
) -> None:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    INSERT INTO placement_metrics (app_id, city, state, placementDate)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(app_id) DO UPDATE SET
        city = excluded.city,
        state = excluded.state,
        placementDate = excluded.placementDate
    """,
        (app_id, city, state, placement_date),
    )
    connection.commit()
    connection.close()


def get_placement_metric(app_id: int):
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT app_id, city, state, placementDate
    FROM placement_metrics
    WHERE app_id = ?
    """,
        (app_id,),
    )
    row = cursor.fetchone()
    connection.close()
    return dict(row) if row else None


def list_placement_metrics() -> list[dict]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT app_id, city, state, placementDate
    FROM placement_metrics
    ORDER BY app_id ASC
    """
    )
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def update_placement_metric(
    app_id: int,
    city: str | None = None,
    state: str | None = None,
    placement_date: str | None = None,
) -> bool:
    updates = []
    values = []

    if city is not None:
        updates.append("city = ?")
        values.append(city)
    if state is not None:
        updates.append("state = ?")
        values.append(state)
    if placement_date is not None:
        updates.append("placementDate = ?")
        values.append(placement_date)

    if len(updates) == 0:
        return False

    values.append(app_id)
    set_clause = ", ".join(updates)

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        f"""
    UPDATE placement_metrics
    SET {set_clause}
    WHERE app_id = ?
    """,
        tuple(values),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def delete_placement_metric(app_id: int) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    DELETE FROM placement_metrics
    WHERE app_id = ?
    """,
        (app_id,),
    )
    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return deleted
