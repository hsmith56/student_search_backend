import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from repositories.base import get_connection

def _parse_favorites(raw_value: Any) -> list[str]:
    if raw_value in (None, ""):
        return []

    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(parsed, list):
        return []

    return [str(item).strip() for item in parsed if str(item).strip() != ""]


def _load_student_lookup(app_ids: list[str]) -> dict[str, dict[str, Any]]:
    numeric_app_ids = [int(app_id) for app_id in app_ids if app_id.isdigit()]
    if len(numeric_app_ids) == 0:
        return {}

    placeholders = ",".join("?" for _ in numeric_app_ids)
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        f"""
        SELECT app_id, first_name, usahsid, id, placement_status
        FROM student_full_view
        WHERE app_id IN ({placeholders})
        """,
        numeric_app_ids,
    )
    rows = cursor.fetchall()
    connection.close()

    return {
        str(row["app_id"]): {
            "student_name": row["first_name"],
            "usahsid": row["usahsid"],
            "beacon_id": row["id"],
            "student_status": row["placement_status"],
        }
        for row in rows
    }


def _load_user_favorites() -> list[dict[str, Any]]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT username, favorites
        FROM users
        ORDER BY username COLLATE NOCASE ASC
        """
    )
    rows = cursor.fetchall()
    connection.close()

    parsed_rows = [
        {
            "username": row["username"],
            "favorite_app_ids": _parse_favorites(row["favorites"]),
        }
        for row in rows
    ]
    all_favorite_app_ids = [
        app_id for row in parsed_rows for app_id in row["favorite_app_ids"]
    ]
    student_lookup = _load_student_lookup(all_favorite_app_ids)

    return [
        {
            "username": row["username"],
            "favorites": [
                student_lookup.get(
                    app_id,
                    {
                        "student_name": "",
                        "usahsid": "",
                        "beacon_id": "",
                        "student_status": "",
                    },
                )
                for app_id in row["favorite_app_ids"]
            ],
        }
        for row in parsed_rows
    ]


def _write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export users and their favorite student application IDs to JSON."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("temp/user_favorites.json"),
        help="JSON output path. Default: temp/user_favorites.json",
    )
    args = parser.parse_args()

    rows = _load_user_favorites()
    _write_json(args.out, rows)
    print(f"Exported {len(rows)} users to {args.out}")


if __name__ == "__main__":
    main()
