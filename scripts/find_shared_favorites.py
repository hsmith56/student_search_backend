import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import settings
from repositories.base import get_connection


def _parse_favorites(raw_favorites: str) -> set[str]:
    if not raw_favorites:
        return set()

    try:
        parsed = json.loads(raw_favorites)
    except json.JSONDecodeError:
        return set()

    if not isinstance(parsed, list):
        return set()

    return {str(item).strip() for item in parsed if str(item).strip() != ""}


def find_shared_favorites() -> list[tuple[str, int]]:
    connection = get_connection(row_factory=True)
    cursor = connection.cursor()
    cursor.execute("SELECT favorites FROM users WHERE favorites IS NOT NULL")
    rows = cursor.fetchall()
    connection.close()

    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(_parse_favorites(row["favorites"]))

    shared = [
        (favorite_id, seen_count)
        for favorite_id, seen_count in counts.items()
        if seen_count > 1
    ]
    shared.sort(key=lambda item: (-item[1], item[0]))
    return shared


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "List favorite student IDs that appear in more than one user's favorites."
        )
    )
    parser.parse_args()

    shared_favorites = find_shared_favorites()
    if not shared_favorites:
        print("No favorite IDs appear in more than 1 user's favorites.")
        return

    for favorite_id, seen_count in shared_favorites:
        print(f"id: {favorite_id}, seen {seen_count} times")


if __name__ == "__main__":
    main()
