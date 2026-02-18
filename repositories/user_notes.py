from repositories.base import get_connection


def upsert_user_note(*, owner_id: str, notes_user_id: str, note_text: str) -> None:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    INSERT INTO user_notes (owner_id, notes_user_id, note_text, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(owner_id, notes_user_id) DO UPDATE SET
        note_text = excluded.note_text,
        updated_at = CURRENT_TIMESTAMP
    """,
        (owner_id, notes_user_id, note_text),
    )
    connection.commit()
    connection.close()


def get_user_note(*, owner_id: str, notes_user_id: str) -> str | None:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT note_text
    FROM user_notes
    WHERE owner_id = ?
      AND notes_user_id = ?
    LIMIT 1
    """,
        (owner_id, notes_user_id),
    )
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    return str(row["note_text"])


def get_user_notes_for_owner(
    *, owner_id: str, notes_user_ids: list[str]
) -> dict[str, str]:
    unique_ids = [item for item in dict.fromkeys(notes_user_ids) if item != ""]
    if len(unique_ids) == 0:
        return {}

    placeholders = ", ".join("?" for _ in unique_ids)
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        f"""
    SELECT notes_user_id, note_text
    FROM user_notes
    WHERE owner_id = ?
      AND notes_user_id IN ({placeholders})
    """,
        (owner_id, *unique_ids),
    )
    rows = cursor.fetchall()
    connection.close()
    return {str(row["notes_user_id"]): str(row["note_text"]) for row in rows}
