import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.logging_config import setup_logging
from integrations.beacon_client import beacon_client
from repositories.admin import initialize_db
from repositories.base import get_connection

logger = logging.getLogger(__name__)

OUTPUT_PATH = ROOT_DIR / "placement_data.json"


def get_placed_app_ids() -> list[int]:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT app_id
            FROM student_full_view
            WHERE LOWER(COALESCE(placement_status, '')) LIKE ?
            ORDER BY app_id
            """,
            ("%place%",),
        )
        rows = cursor.fetchall()
    return [int(row["app_id"]) for row in rows]


def fetch_host_information(app_id: int) -> dict[str, Any]:
    response = beacon_client.get(f"/beacon/participant/hostinformation/{app_id}")
    result: dict[str, Any] = {
        "app_id": app_id,
        "status_code": response.status_code,
    }

    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    if response.status_code >= 400:  # ty:ignore[unsupported-operator]
        logger.warning(
            "Host information request failed for app_id=%s status_code=%s",
            app_id,
            response.status_code,
        )
    result["payload"] = payload
    return result


def main() -> None:
    setup_logging()
    initialize_db()

    app_ids = get_placed_app_ids()
    logger.info("Found %s placed students in student_full_view", len(app_ids))

    results = [fetch_host_information(app_id) for app_id in app_ids]
    export = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "placed_student_count": len(app_ids),
        "results": results,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as output_file:
        json.dump(export, output_file, ensure_ascii=False, indent=2)

    logger.info("Wrote placement data to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
