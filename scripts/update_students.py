import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from requests.adapters import HTTPAdapter

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
DEFAULT_THREADS = 8


def _authenticate_beacon_client() -> None:
    beacon_client._get_token()


def _configure_beacon_client_pool(max_workers: int) -> None:
    adapter = HTTPAdapter(pool_connections=max_workers, pool_maxsize=max_workers)
    beacon_client.session.mount("https://", adapter)
    beacon_client.session.mount("http://", adapter)


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


def update_states(app_ids: list[int], max_workers: int) -> tuple[int, int]:
    updates_by_app_id: dict[int, str] = {}
    failed = 0

    # NOTE: With max_workers=1, ThreadPoolExecutor still runs work on a background
    # thread. Some environments exhibit intermittent SSL failures only when the
    # TLS handshake happens off the main thread, so avoid the executor in that case.
    if max_workers <= 1:
        for index, app_id in enumerate(app_ids, start=1):
            try:
                states = _fetch_states_for_app(app_id)
                states_json = json.dumps(states)
                updates_by_app_id[app_id] = states_json
                logger.info("State values app_id=%s states=%s", app_id, states_json)
            except Exception as exc:
                failed += 1
                logger.warning("State update failed for app_id=%s: %s", app_id, exc)

            if index % 100 == 0:
                logger.info(
                    "State fetch progress: processed=%s queued=%s failed=%s",
                    index,
                    len(updates_by_app_id),
                    failed,
                )
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_fetch_states_for_app, app_id): app_id for app_id in app_ids
            }
            for index, future in enumerate(as_completed(futures), start=1):
                app_id = futures[future]
                try:
                    states = future.result()
                    states_json = json.dumps(states)
                    updates_by_app_id[app_id] = states_json
                    logger.info("State values app_id=%s states=%s", app_id, states_json)
                except Exception as exc:
                    failed += 1
                    logger.warning("State update failed for app_id=%s: %s", app_id, exc)

                if index % 100 == 0:
                    logger.info(
                        "State fetch progress: processed=%s queued=%s failed=%s",
                        index,
                        len(updates_by_app_id),
                        failed,
                    )

    with get_connection() as connection:
        cursor = connection.cursor()
        for app_id in app_ids:
            states_json = updates_by_app_id.get(app_id)
            if states_json is None:
                continue
            cursor.execute(
                """
                UPDATE student_full_view
                SET states = ?
                WHERE app_id = ?
                """,
                (states_json, app_id),
            )
        connection.commit()
    return len(updates_by_app_id), failed


def update_usahsids(app_ids: list[int], max_workers: int) -> tuple[int, int]:
    updates_by_app_id: dict[int, str] = {}
    failed = 0

    if max_workers <= 1:
        for index, app_id in enumerate(app_ids, start=1):
            try:
                updates_by_app_id[app_id] = _fetch_usahsid_for_app(app_id)
            except Exception as exc:
                failed += 1
                logger.warning("usahsid update failed for app_id=%s: %s", app_id, exc)

            if index % 100 == 0:
                logger.info(
                    "usahsid fetch progress: processed=%s queued=%s failed=%s",
                    index,
                    len(updates_by_app_id),
                    failed,
                )
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_fetch_usahsid_for_app, app_id): app_id for app_id in app_ids
            }
            for index, future in enumerate(as_completed(futures), start=1):
                app_id = futures[future]
                try:
                    updates_by_app_id[app_id] = future.result()
                except Exception as exc:
                    failed += 1
                    logger.warning("usahsid update failed for app_id=%s: %s", app_id, exc)

                if index % 100 == 0:
                    logger.info(
                        "usahsid fetch progress: processed=%s queued=%s failed=%s",
                        index,
                        len(updates_by_app_id),
                        failed,
                    )

    with get_connection() as connection:
        cursor = connection.cursor()
        for app_id in app_ids:
            usahsid = updates_by_app_id.get(app_id)
            if usahsid is None:
                continue
            cursor.execute(
                """
                UPDATE student_full_view
                SET usahsid = ?
                WHERE app_id = ?
                """,
                (usahsid, app_id),
            )
        connection.commit()
    return len(updates_by_app_id), failed


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
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_THREADS,
        help="Number of thread pool workers for Beacon HTTP requests (default: 8).",
    )
    args = parser.parse_args()

    if not args.state and not args.usahsid:
        parser.error("Pass at least one flag: --state or --usahsid")

    setup_logging()
    initialize_db()
    max_workers = max(1, int(args.threads))
    _configure_beacon_client_pool(max_workers=max_workers)
    _authenticate_beacon_client()

    app_ids = _get_filtered_student_app_ids(args.query)
    logger.info("Loaded %s target students from student_full_view", len(app_ids))
    logger.info(
        "Running update script with flags state=%s usahsid=%s query=%s",
        args.state,
        args.usahsid,
        args.query,
    )
    logger.info("Beacon request threads=%s", max_workers)

    if len(app_ids) == 0:
        logger.info("No students matched the provided filter. Exiting.")
        return

    if args.state:
        state_success, state_failures = update_states(app_ids, max_workers=max_workers)
        logger.info(
            "State update complete. updated=%s failed=%s",
            state_success,
            state_failures,
        )

    if args.usahsid:
        usahsid_success, usahsid_failures = update_usahsids(
            app_ids, max_workers=max_workers
        )
        logger.info(
            "usahsid update complete. updated=%s failed=%s",
            usahsid_success,
            usahsid_failures,
        )


if __name__ == "__main__":
    main()
