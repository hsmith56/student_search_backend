import hashlib
import json
import secrets
import sqlite3
import string

from repositories.base import get_connection

_CODE_LETTERS = string.ascii_uppercase
_CODE_DIGITS = string.digits
_VALID_ACCOUNT_TYPES = {"lc", "rpm"}


def _normalize_code(code: str) -> str:
    return code.strip().upper()


def hash_signup_code(code: str) -> str:
    normalized = _normalize_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_signup_code(account_type: str) -> str:
    account_type = account_type.strip().lower()
    if account_type not in _VALID_ACCOUNT_TYPES:
        raise ValueError("Invalid account_type")

    prefix = "LC" if account_type == "lc" else "RPM"
    letters = "".join(secrets.choice(_CODE_LETTERS) for _ in range(4))
    digits = "".join(secrets.choice(_CODE_DIGITS) for _ in range(4))
    return f"{prefix}-{letters}-{digits}"


def _parse_states(states_raw: str) -> list[str]:
    try:
        parsed = json.loads(states_raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return []


def _to_signup_dict(row: sqlite3.Row, auth_code: str | None = None) -> dict:
    item = dict(row)
    stored_auth_code = auth_code if auth_code is not None else item.get("auth_code")
    payload = {
        "id": item["id"],
        "first_name": item["first_name"],
        "last_name": item["last_name"],
        "email": item["email"],
        "states": _parse_states(item["states"]),
        "account_type": item["account_type"],
        "code_used": bool(item["code_used"]),
        "submitter_id": item["submitter_id"],
        "created_at": item["created_at"],
        "used_at": item["used_at"],
        "auth_code": stored_auth_code,
        "notes_text": item.get("notes"),
    }
    return payload


def create_signup_request(
    *,
    first_name: str,
    last_name: str,
    email: str | None,
    states: list[str],
    account_type: str,
    submitter_id: str,
    max_attempts: int = 10,
) -> dict:
    normalized_type = account_type.strip().lower()
    if normalized_type not in _VALID_ACCOUNT_TYPES:
        raise ValueError("Invalid account_type")

    states_json = json.dumps(states)

    for _ in range(max_attempts):
        auth_code = generate_signup_code(account_type=normalized_type)
        auth_code_hash = hash_signup_code(auth_code)
        connection = get_connection(row_factory=True)
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
            INSERT INTO user_signup (
                first_name,
                last_name,
                email,
                states,
                notes,
                auth_code,
                auth_code_hash,
                account_type,
                submitter_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    first_name,
                    last_name,
                    email,
                    states_json,
                    None,
                    auth_code,
                    auth_code_hash,
                    normalized_type,
                    submitter_id,
                ),
            )
            signup_id = cursor.lastrowid
            connection.commit()

            cursor.execute(
                """
            SELECT id, first_name, last_name, email, states, account_type, code_used,
                   submitter_id, created_at, used_at, auth_code, notes
            FROM user_signup
            WHERE id = ?
            """,
                (signup_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Failed to load created signup request")
            return _to_signup_dict(row=row, auth_code=auth_code)
        except sqlite3.IntegrityError as exc:
            if "auth_code_hash" in str(exc):
                continue
            raise
        finally:
            connection.close()

    raise RuntimeError("Failed to generate unique signup code")


def list_signup_requests_for_user(*, requester_id: str, requester_role: str) -> list[dict]:
    normalized_role = requester_role.strip().lower()
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    if normalized_role == "admin":
        cursor.execute(
            """
        SELECT id, first_name, last_name, email, states, account_type, code_used,
               submitter_id, created_at, used_at, auth_code, notes
        FROM user_signup
        ORDER BY id DESC
        """
        )
    else:
        cursor.execute(
            """
        SELECT id, first_name, last_name, email, states, account_type, code_used,
               submitter_id, created_at, used_at, auth_code, notes
        FROM user_signup
        WHERE submitter_id = ?
        ORDER BY id DESC
        """,
            (requester_id,),
        )

    rows = cursor.fetchall()
    connection.close()
    return [_to_signup_dict(row=row) for row in rows]


def get_unused_signup_by_code(code: str) -> dict | None:
    code_hash = hash_signup_code(code=code)
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
    SELECT id, first_name, last_name, email, states, account_type, code_used,
           submitter_id, created_at, used_at, auth_code, notes
    FROM user_signup
    WHERE auth_code_hash = ?
      AND code_used = 0
    ORDER BY id DESC
    LIMIT 1
    """,
        (code_hash,),
    )
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    return _to_signup_dict(row=row)


def mark_signup_code_used(signup_id: int) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
    UPDATE user_signup
    SET code_used = 1,
        used_at = CURRENT_TIMESTAMP
    WHERE id = ?
      AND code_used = 0
    """,
        (signup_id,),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def update_signup_request_for_user(
    *,
    signup_id: int,
    requester_id: str,
    requester_role: str,
    states: list[str] | None,
    notes_text: str | None,
    update_states: bool,
    update_notes: bool,
) -> dict | None:
    if update_states is False and update_notes is False:
        return None

    normalized_role = requester_role.strip().lower()

    connection = get_connection(row_factory=True)
    cursor = connection.cursor()

    if normalized_role == "admin":
        cursor.execute(
            """
        SELECT id
        FROM user_signup
        WHERE id = ?
        LIMIT 1
        """,
            (signup_id,),
        )
    else:
        cursor.execute(
            """
        SELECT id
        FROM user_signup
        WHERE id = ?
          AND submitter_id = ?
        LIMIT 1
        """,
            (signup_id, requester_id),
        )

    if cursor.fetchone() is None:
        connection.close()
        return None

    updates: list[str] = []
    params: list[object] = []

    if update_states:
        updates.append("states = ?")
        params.append(json.dumps(states if states is not None else []))

    if update_notes:
        updates.append("notes = ?")
        params.append(notes_text if notes_text is not None else "")

    update_query = f"UPDATE user_signup SET {', '.join(updates)} WHERE id = ?"
    params.append(signup_id)
    if normalized_role != "admin":
        update_query += " AND submitter_id = ?"
        params.append(requester_id)

    cursor.execute(update_query, tuple(params))
    connection.commit()

    if normalized_role == "admin":
        cursor.execute(
            """
        SELECT id, first_name, last_name, email, states, account_type, code_used,
               submitter_id, created_at, used_at, auth_code, notes
        FROM user_signup
        WHERE id = ?
        LIMIT 1
        """,
            (signup_id,),
        )
    else:
        cursor.execute(
            """
        SELECT id, first_name, last_name, email, states, account_type, code_used,
               submitter_id, created_at, used_at, auth_code, notes
        FROM user_signup
        WHERE id = ?
          AND submitter_id = ?
        LIMIT 1
        """,
            (signup_id, requester_id),
        )

    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    return _to_signup_dict(row=row)
