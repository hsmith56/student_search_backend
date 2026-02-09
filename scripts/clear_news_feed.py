import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from repositories.admin import initialize_db
from core.logging_config import setup_logging
from repositories.student_placement_events import clear_student_placement_events

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete all rows from the news feed table (student_placement_events)."
    )
    args = parser.parse_args()
    del args

    setup_logging()
    initialize_db()
    deleted_count = clear_student_placement_events()
    logger.info("Cleared news feed table. deleted_events=%s", deleted_count)


if __name__ == "__main__":
    main()
