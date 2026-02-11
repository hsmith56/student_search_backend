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


def get_placed_students() -> list[dict[str, int]]:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, app_id
            FROM student_full_view
            WHERE LOWER(COALESCE(placement_status, '')) LIKE ?
            ORDER BY app_id
            """,
            ("%place%",),
        )
        rows = cursor.fetchall()
    return [{"id": int(row["id"]), "app_id": int(row["app_id"])} for row in rows]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _needs_placement_fallback(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return True
    placement_date = payload.get("placementDate")
    placement_status = str(payload.get("placementStatus", "")).lower()
    return _is_blank(placement_date) or ("pending" in placement_status)


def _sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        payload.pop("hostFamilyName", None)
        payload.pop("host", None)
    return payload


def _apply_placement_fallback(
    host_payload: Any, student_id: int, app_id: int
) -> tuple[Any, bool]:
    response = beacon_client.get(f"/beacon/Placement/{student_id}")
    if response.status_code >= 400:  # ty:ignore[unsupported-operator]
        logger.warning(
            "Placement fallback request failed for id=%s app_id=%s status_code=%s",
            student_id,
            app_id,
            response.status_code,
        )
        return host_payload, False

    try:
        placement_payload = response.json()
    except ValueError:
        logger.warning(
            "Placement fallback response was not JSON for id=%s app_id=%s",
            student_id,
            app_id,
        )
        return host_payload, False

    if not isinstance(placement_payload, dict):
        return host_payload, False

    pending_date = placement_payload.get("pendingPlacementResolutionDate")

    if _is_blank(pending_date):
        return host_payload, False

    if not isinstance(host_payload, dict):
        host_payload = {}

    host_payload["placementDate"] = pending_date
    host_payload["city"] = ""
    host_payload["state"] = ""
    return host_payload, True


def fetch_host_information(student_id: int, app_id: int) -> dict[str, Any]:
    response = beacon_client.get(f"/beacon/participant/hostinformation/{app_id}")
    result: dict[str, Any] = {
        "id": student_id,
        "app_id": app_id,
        "status_code": response.status_code,
        "placement_fallback_used": False,
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

    payload = _sanitize_payload(payload)

    if _needs_placement_fallback(payload):
        payload, fallback_used = _apply_placement_fallback(
            host_payload=payload,
            student_id=student_id,
            app_id=app_id,
        )
        result["placement_fallback_used"] = fallback_used

    result["payload"] = _sanitize_payload(payload)
    return result


def main() -> None:
    setup_logging()
    initialize_db()

    placed_students = get_placed_students()
    logger.info("Found %s placed students in student_full_view", len(placed_students))

    results = [
        fetch_host_information(student["id"], student["app_id"])
        for student in placed_students
    ]
    fallback_count = sum(
        1 for result in results if result["placement_fallback_used"] is True
    )
    export = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "placed_student_count": len(placed_students),
        "placement_fallback_count": fallback_count,
        "results": results,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as output_file:
        json.dump(export, output_file, ensure_ascii=False, indent=2)

    logger.info("Wrote placement data to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
