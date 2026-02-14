import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.logging_config import setup_logging
from integrations.beacon_client import beacon_client
from repositories.admin import initialize_db
from repositories.base import get_connection
from utils.beacon_refresh_stage2 import (
    get_basic_information,
    get_category_mappings,
    get_placement_requests,
)

logger = logging.getLogger(__name__)


def _authenticate_beacon_client() -> None:
    beacon_client._get_token()


def _get_all_student_app_ids() -> list[int]:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT app_id FROM student_full_view ORDER BY app_id")
        rows = cursor.fetchall()
    return [int(row["app_id"]) for row in rows]


def _get_filtered_student_app_ids(query: Optional[str]) -> list[int]:
    if query is None or query.strip() == "":
        return _get_all_student_app_ids()

    like_value = f"%{query.strip().lower()}%"
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT app_id
            FROM student_full_view
            WHERE LOWER(COALESCE(usahsid, '')) LIKE ?
            ORDER BY app_id
            """,
            (like_value,),
        )
        rows = cursor.fetchall()
    return [int(row["app_id"]) for row in rows]


def _dedupe_states(states: list[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for state in states:
        if state is None:
            continue
        normalized = str(state).strip()
        if normalized == "" or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _fetch_states_for_app(app_id: int) -> list[str]:
    mappings_response = get_category_mappings(app_id)
    if mappings_response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(
            f"Failed to fetch category mappings for app_id={app_id}. "
            f"status_code={mappings_response.status_code}"
        )

    mappings_payload = mappings_response.json()
    if not isinstance(mappings_payload, list):
        raise ValueError(
            f"Category mappings payload was not a list for app_id={app_id}"
        )

    mappings = {
        item.get("sectionName"): item.get("id")
        for item in mappings_payload
        if isinstance(item, dict)
    }
    placement_section_id = mappings.get("hsjPlacementOptions")
    if placement_section_id is None:
        return []

    placement_states, *_ = get_placement_requests(placement_section_id)
    return _dedupe_states(placement_states)


def _fetch_usahsid_for_app(app_id: int) -> str:
    basic_info_response = get_basic_information(app_id)
    if basic_info_response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(
            f"Failed to fetch basic information for app_id={app_id}. "
            f"status_code={basic_info_response.status_code}"
        )

    basic_info_payload = basic_info_response.json()
    if not isinstance(basic_info_payload, dict):
        raise ValueError(
            f"Basic information payload was not an object for app_id={app_id}"
        )

    usahsid = basic_info_payload.get("usahsId") or basic_info_payload.get("usaHsId") or ""
    return str(usahsid).strip()


def update_states(app_ids: list[int]) -> tuple[int, int]:
    updated = 0
    failed = 0
    with get_connection() as connection:
        cursor = connection.cursor()
        for index, app_id in enumerate(app_ids, start=1):
            try:
                states = _fetch_states_for_app(app_id)
                logger.info(
                    "State values app_id=%s states=%s",
                    app_id,
                    json.dumps(states),
                )
                cursor.execute(
                    """
                    UPDATE student_full_view
                    SET states = ?
                    WHERE app_id = ?
                    """,
                    (json.dumps(states), app_id),
                )
                updated += 1
            except Exception as exc:
                failed += 1
                logger.warning("State update failed for app_id=%s: %s", app_id, exc)

            if index % 100 == 0:
                logger.info(
                    "State progress: processed=%s updated=%s failed=%s",
                    index,
                    updated,
                    failed,
                )
        connection.commit()
    return updated, failed


def update_usahsids(app_ids: list[int]) -> tuple[int, int]:
    updated = 0
    failed = 0
    with get_connection() as connection:
        cursor = connection.cursor()
        for index, app_id in enumerate(app_ids, start=1):
            try:
                usahsid = _fetch_usahsid_for_app(app_id)
                cursor.execute(
                    """
                    UPDATE student_full_view
                    SET usahsid = ?
                    WHERE app_id = ?
                    """,
                    (usahsid, app_id),
                )
                updated += 1
            except Exception as exc:
                failed += 1
                logger.warning("usahsid update failed for app_id=%s: %s", app_id, exc)

            if index % 100 == 0:
                logger.info(
                    "usahsid progress: processed=%s updated=%s failed=%s",
                    index,
                    updated,
                    failed,
                )
        connection.commit()
    return updated, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-time Beacon sync for student_full_view. "
            "Use --state to refresh states and --usahsid to refresh usahsid."
        )
    )
    parser.add_argument(
        "--state",
        action="store_true",
        help="Refresh the student_full_view.states field for every student.",
    )
    parser.add_argument(
        "--usahsid",
        action="store_true",
        help="Refresh the student_full_view.usahsid field for every student.",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Only update students whose current usahsid contains this value (case-insensitive).",
    )
    args = parser.parse_args()

    if not args.state and not args.usahsid:
        parser.error("Pass at least one flag: --state or --usahsid")

    setup_logging()
    initialize_db()
    _authenticate_beacon_client()

    app_ids = _get_filtered_student_app_ids(args.query)
    logger.info("Loaded %s target students from student_full_view", len(app_ids))
    logger.info(
        "Running update script with flags state=%s usahsid=%s query=%s",
        args.state,
        args.usahsid,
        args.query,
    )

    if len(app_ids) == 0:
        logger.info("No students matched the provided filter. Exiting.")
        return

    if args.state:
        state_success, state_failures = update_states(app_ids)
        logger.info(
            "State update complete. updated=%s failed=%s",
            state_success,
            state_failures,
        )

    if args.usahsid:
        usahsid_success, usahsid_failures = update_usahsids(app_ids)
        logger.info(
            "usahsid update complete. updated=%s failed=%s",
            usahsid_success,
            usahsid_failures,
        )


if __name__ == "__main__":
    main()
