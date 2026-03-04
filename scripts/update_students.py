import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from requests.adapters import HTTPAdapter

from core.logging_config import setup_logging
from integrations.beacon_client import beacon_client
from repositories.admin import initialize_db
from repositories.base import get_connection
from utils.beacon_refresh_stage2 import (
    get_basic_information,
    get_category_mappings,
    get_placement_requests,
    run_stage_2_multi_threaded,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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


def _get_filtered_stage_2_students(query: str) -> list[dict[str, Any]]:
    like_value = f"%{query.strip().lower()}%"
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                id,
                usaHsId,
                applicationId,
                participantId,
                agencyId,
                placementStatusId,
                placementStatusName,
                paxNameFirst,
                paxGender
            FROM student_basic_overview
            WHERE LOWER(COALESCE(usaHsId, '')) LIKE ?
            ORDER BY applicationId
            """,
            (like_value,),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def _get_stage_2_students_with_null_usahsid() -> list[dict[str, Any]]:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                id,
                usaHsId,
                applicationId,
                participantId,
                agencyId,
                placementStatusId,
                placementStatusName,
                paxNameFirst,
                paxGender
            FROM student_basic_overview
            WHERE usaHsId IS NULL
            ORDER BY applicationId
            """
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def _get_basic_app_ids_with_empty_usahsid() -> list[int]:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT applicationId
            FROM student_basic_overview
            WHERE usaHsId IS NULL OR TRIM(usaHsId) = ''
            ORDER BY applicationId
            """
        )
        rows = cursor.fetchall()
    return [int(row["applicationId"]) for row in rows]


def drop_students_from_full_and_basic_by_app_ids(app_ids: list[int]) -> tuple[int, int]:
    if len(app_ids) == 0:
        return 0, 0

    placeholders = ",".join("?" for _ in app_ids)
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"DELETE FROM student_full_view WHERE app_id IN ({placeholders})",
            app_ids,
        )
        full_deleted_rows = cursor.rowcount
        cursor.execute(
            f"DELETE FROM student_basic_overview WHERE applicationId IN ({placeholders})",
            app_ids,
        )
        basic_deleted_rows = cursor.rowcount
        connection.commit()

    return max(0, int(full_deleted_rows)), max(0, int(basic_deleted_rows))


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

    usahsid = (
        basic_info_payload.get("usahsId") or basic_info_payload.get("usaHsId") or ""
    )
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
                pool.submit(_fetch_usahsid_for_app, app_id): app_id
                for app_id in app_ids
            }
            for index, future in enumerate(as_completed(futures), start=1):
                app_id = futures[future]
                try:
                    updates_by_app_id[app_id] = future.result()
                except Exception as exc:
                    failed += 1
                    logger.warning(
                        "usahsid update failed for app_id=%s: %s", app_id, exc
                    )

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
            "Use --state to refresh states, --usahsid to refresh usahsid, "
            "--all to run full stage_2 hydration by query, "
            "--null to run full stage_2 for students with null usaHsId in "
            "student_basic_overview, or --drop-and-clean to remove matching "
            "rows from full and basic views for empty usaHsId records in basic overview."
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
        "--all",
        action="store_true",
        help="Run full stage_2 hydration for students matched by --query.",
    )
    parser.add_argument(
        "--null",
        action="store_true",
        help="Run full stage_2 hydration for students in student_basic_overview where usaHsId is null.",
    )
    parser.add_argument(
        "--drop-and-clean",
        action="store_true",
        help=(
            "Find students with empty usaHsId in student_basic_overview and "
            "drop matching student rows from student_full_view and student_basic_overview."
        ),
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help=(
            "Case-insensitive usahsid filter. "
            "For --all, this is required and matched against student_basic_overview.usaHsId."
        ),
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_THREADS,
        help="Number of thread pool workers for Beacon HTTP requests (default: 8).",
    )
    args = parser.parse_args()

    if (
        not args.state
        and not args.usahsid
        and not args.all
        and not args.null
        and not args.drop_and_clean
    ):
        parser.error(
            "Pass at least one flag: --state, --usahsid, --all, --null, or --drop-and-clean"
        )
    if args.drop_and_clean and (args.state or args.usahsid or args.all or args.null):
        parser.error(
            "--drop-and-clean cannot be combined with --state, --usahsid, --all, or --null"
        )
    if args.drop_and_clean and args.query is not None and args.query.strip() != "":
        parser.error("--drop-and-clean cannot be combined with --query")
    if args.null and (args.state or args.usahsid or args.all):
        parser.error("--null cannot be combined with --state, --usahsid, or --all")
    if args.null and args.query is not None and args.query.strip() != "":
        parser.error("--null cannot be combined with --query")
    if args.all and (args.state or args.usahsid):
        parser.error("--all cannot be combined with --state or --usahsid")
    if args.all and (args.query is None or args.query.strip() == ""):
        parser.error("Pass --query when using --all (example: --all --query PLA26526)")

    setup_logging()
    initialize_db()
    max_workers = max(1, int(args.threads))

    logger.info(
        "Running update script with flags state=%s usahsid=%s all=%s null=%s drop_and_clean=%s query=%s",
        args.state,
        args.usahsid,
        args.all,
        args.null,
        args.drop_and_clean,
        args.query,
    )

    if args.drop_and_clean:
        basic_app_ids = _get_basic_app_ids_with_empty_usahsid()
        logger.info(
            "Loaded %s student_basic_overview rows with empty usaHsId",
            len(basic_app_ids),
        )
        if len(basic_app_ids) == 0:
            logger.info("No students matched the provided filter. Exiting.")
            return
        full_deleted_count, basic_deleted_count = (
            drop_students_from_full_and_basic_by_app_ids(basic_app_ids)
        )
        logger.info(
            "drop-and-clean complete. matched_basic_rows=%s dropped_from_full_view=%s dropped_from_basic_view=%s",
            len(basic_app_ids),
            full_deleted_count,
            basic_deleted_count,
        )
        return

    logger.info("Beacon request threads=%s", max_workers)
    _configure_beacon_client_pool(max_workers=max_workers)
    _authenticate_beacon_client()

    if args.null:
        stage_2_students = _get_stage_2_students_with_null_usahsid()
        logger.info(
            "Loaded %s target students from student_basic_overview with null usaHsId for stage_2",
            len(stage_2_students),
        )
        if len(stage_2_students) == 0:
            logger.info("No students matched the provided filter. Exiting.")
            return
        run_stage_2_multi_threaded(stage_2_students)
        logger.info("stage_2 null update complete. processed=%s", len(stage_2_students))
        return

    if args.all:
        stage_2_query = args.query.strip() if args.query is not None else ""
        stage_2_students = _get_filtered_stage_2_students(stage_2_query)
        logger.info(
            "Loaded %s target students from student_basic_overview for stage_2",
            len(stage_2_students),
        )
        if len(stage_2_students) == 0:
            logger.info("No students matched the provided filter. Exiting.")
            return
        run_stage_2_multi_threaded(stage_2_students)
        logger.info("stage_2 update complete. processed=%s", len(stage_2_students))
        return

    app_ids = _get_filtered_student_app_ids(args.query)
    logger.info("Loaded %s target students from student_full_view", len(app_ids))
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
