import argparse
import logging

from core.logging_config import setup_logging
from repositories.admin import initialize_db
from repositories.base import get_connection
from integrations.beacon_client import beacon_client
from utils.beacon_refresh_stage2 import run_stage_2_multi_threaded

logger = logging.getLogger(__name__)


def _authenticate_beacon_client() -> None:
    beacon_client._get_token()


def _get_all_students_for_stage_2() -> list[dict]:
    with get_connection(row_factory=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                b.id,
                b.usaHsId,
                b.applicationId,
                b.participantId,
                b.agencyId,
                b.placementStatusId,
                b.placementStatusName,
                b.paxNameFirst,
                b.paxGender
            FROM student_basic_overview b
            INNER JOIN student_full_view f
                ON b.applicationId = f.app_id
            WHERE b.placementStatusName = "Unassigned"
            ORDER BY b.applicationId
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _get_students_for_stage_2(limit: int | None = None) -> list[dict]:
    students = _get_all_students_for_stage_2()
    if limit is not None and limit > 0:
        return students[:limit]
    return students


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run stage-2 Beacon hydration for every student currently present in "
            "student_full_view, then persist updated tuition_placement (and other "
            "stage-2 fields) back to the SQL DB."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N students (useful for a partial test run).",
    )
    parser.add_argument(
        "--skip-auth",
        action="store_true",
        help=(
            "Skip explicit Beacon auth call. Useful only when using an already-valid "
            "in-process auth token."
        ),
    )
    args = parser.parse_args()

    setup_logging()
    initialize_db()

    students = _get_students_for_stage_2(limit=args.limit)
    logger.info(
        "Loaded %s target students from student_full_view for stage-2 hydration.",
        len(students),
    )
    if not students:
        logger.info("No matching students found. Exiting.")
        return

    if not args.skip_auth:
        _authenticate_beacon_client()

    run_stage_2_multi_threaded(students)

    logger.info(
        "tuition_placement backfill completed for all matched students. processed=%s",
        len(students),
    )


if __name__ == "__main__":
    main()
