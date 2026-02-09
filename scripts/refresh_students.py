import logging

from core.logging_config import setup_logging
from routers.students import apply_filters
from repositories.admin import initialize_db, update_time
from utils.beacon_refresh_stage1 import get_updates_from_beacon
from utils.beacon_refresh_stage2 import run_stage_2_multi_threaded

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    initialize_db()

    students_needing_stage_2 = get_updates_from_beacon()
    if len(students_needing_stage_2) > 0:
        run_stage_2_multi_threaded(students_needing_stage_2)

    update_time()
    apply_filters.cache_clear()
    logger.info(
        "Student refresh completed. stage_2_processed=%s",
        len(students_needing_stage_2),
    )


if __name__ == "__main__":
    main()
