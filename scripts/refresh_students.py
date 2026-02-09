import logging

from routers.students import apply_filters
from utils import db
from utils.beacon_refresh_stage1 import get_updates_from_beacon
from utils.beacon_refresh_stage2 import run_stage_2_multi_threaded


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db.initialize_db()

    students_needing_stage_2 = get_updates_from_beacon()
    if len(students_needing_stage_2) > 0:
        run_stage_2_multi_threaded(students_needing_stage_2)

    db.update_time()
    apply_filters.cache_clear()
    logging.info(
        "Student refresh completed. stage_2_processed=%s",
        len(students_needing_stage_2),
    )


if __name__ == "__main__":
    main()
