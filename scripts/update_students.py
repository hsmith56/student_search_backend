import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from requests.exceptions import RequestException

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import settings
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


@dataclass(frozen=True)
class StateUpdate:
    app_id: int
    states_json: str


@dataclass(frozen=True)
class UsahsIdUpdate:
    app_id: int
    usahsid: str


RETRYABLE_STATUS_CODES = {401, 403, 408, 425, 429, 500, 502, 503, 504}
T = TypeVar("T")


def _configure_beacon_client_pool(max_workers: int) -> None:
    beacon_client.configure_pool(
        pool_connections=max_workers,
        pool_maxsize=max_workers,
    )


def _authenticate_beacon_client() -> None:
    beacon_client._get_token()


def _get_all_student_app_ids() -> list[int]:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT app_id FROM student_full_view ORDER BY app_id")
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


def _status_code_from_error(exc: Exception) -> int | None:
    match = re.search(r"status_code=(\d+)", str(exc))
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, RequestException):
        return True

    status_code = _status_code_from_error(exc)
    if status_code is not None and status_code in RETRYABLE_STATUS_CODES:
        return True

    lowered = str(exc).lower()
    return any(
        text in lowered for text in ("ssl", "timeout", "connection reset", "temporary")
    )


def _with_retry(
    operation_name: str,
    app_id: int,
    max_attempts: int,
    operation: Callable[[], T],
) -> T:
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt >= max_attempts or not _is_retryable_error(exc):
                raise
            sleep_for = max(
                1, settings.beacon_retry_backoff_seconds * (2 ** (attempt - 1))
            )
            logger.warning(
                "%s transient failure for app_id=%s attempt=%s/%s retrying in %ss: %s",
                operation_name,
                app_id,
                attempt,
                max_attempts,
                sleep_for,
                exc,
            )
            time.sleep(sleep_for)
    raise RuntimeError("Retry loop exhausted unexpectedly")


def _fetch_state_update(app_id: int) -> StateUpdate:
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

    states: list[Any] = []
    if placement_section_id is not None:
        placement_states, *_ = get_placement_requests(placement_section_id)
        states = placement_states

    return StateUpdate(
        app_id=app_id,
        states_json=json.dumps(_dedupe_states(states)),
    )


def _fetch_usahsid_update(app_id: int) -> UsahsIdUpdate:
    basic_info_response = get_basic_information(app_id)
    if basic_info_response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(
            f"Failed to fetch basic information for app_id={app_id}. "
            f"status_code={basic_info_response.status_code}"
        )

    basic_info_payload = basic_info_response.json()
    if not isinstance(basic_info_payload, dict):
        raise ValueError(f"Basic information payload was not an object for app_id={app_id}")

    usahsid = basic_info_payload.get("usahsId") or basic_info_payload.get("usaHsId") or ""
    return UsahsIdUpdate(app_id=app_id, usahsid=str(usahsid).strip())


def update_states(
    app_ids: list[int], max_workers: int, max_attempts: int
) -> tuple[int, int]:
    updates: list[StateUpdate] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _with_retry,
                "State fetch",
                app_id,
                max_attempts,
                lambda app_id=app_id: _fetch_state_update(app_id),
            ): app_id
            for app_id in app_ids
        }
        for future in as_completed(futures):
            app_id = futures[future]
            try:
                updates.append(future.result())
            except Exception as exc:
                failures += 1
                logger.warning("State update fetch failed for app_id=%s: %s", app_id, exc)

    with get_connection() as connection:
        cursor = connection.cursor()
        for update in updates:
            cursor.execute(
                """
                UPDATE student_full_view
                SET states = ?
                WHERE app_id = ?
                """,
                (update.states_json, update.app_id),
            )
        connection.commit()

    return len(updates), failures


def update_usahsids(
    app_ids: list[int], max_workers: int, max_attempts: int
) -> tuple[int, int]:
    updates: list[UsahsIdUpdate] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _with_retry,
                "usahsid fetch",
                app_id,
                max_attempts,
                lambda app_id=app_id: _fetch_usahsid_update(app_id),
            ): app_id
            for app_id in app_ids
        }
        for future in as_completed(futures):
            app_id = futures[future]
            try:
                updates.append(future.result())
            except Exception as exc:
                failures += 1
                logger.warning(
                    "usahsid update fetch failed for app_id=%s: %s", app_id, exc
                )

    with get_connection() as connection:
        cursor = connection.cursor()
        for update in updates:
            cursor.execute(
                """
                UPDATE student_full_view
                SET usahsid = ?
                WHERE app_id = ?
                """,
                (update.usahsid, update.app_id),
            )
        connection.commit()

    return len(updates), failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-time threaded Beacon sync for student_full_view. "
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
        "--threads",
        type=int,
        default=settings.beacon_threads,
        help="Number of worker threads used for Beacon requests.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=max(2, settings.beacon_max_retries),
        help="Maximum per-student retry attempts for transient Beacon failures.",
    )
    args = parser.parse_args()

    if not args.state and not args.usahsid:
        parser.error("Pass at least one flag: --state or --usahsid")

    setup_logging()
    initialize_db()

    max_workers = max(1, int(args.threads))
    max_attempts = max(1, int(args.attempts))
    _configure_beacon_client_pool(max_workers=max_workers)

    _authenticate_beacon_client()
    app_ids = _get_all_student_app_ids()
    logger.info("Loaded %s students from student_full_view", len(app_ids))
    logger.info(
        "Running update script with flags state=%s usahsid=%s threads=%s",
        args.state,
        args.usahsid,
        max_workers,
    )
    logger.info("Retry attempts per student=%s", max_attempts)

    if args.state:
        state_success, state_failures = update_states(
            app_ids, max_workers=max_workers, max_attempts=max_attempts
        )
        logger.info(
            "State update complete. updated=%s failed=%s",
            state_success,
            state_failures,
        )

    if args.usahsid:
        usahsid_success, usahsid_failures = update_usahsids(
            app_ids, max_workers=max_workers, max_attempts=max_attempts
        )
        logger.info(
            "usahsid update complete. updated=%s failed=%s",
            usahsid_success,
            usahsid_failures,
        )


if __name__ == "__main__":
    main()
