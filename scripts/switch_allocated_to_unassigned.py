import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.logging_config import setup_logging
from repositories.students import randomly_switch_allocated_students_to_unassigned

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Randomly switch allocated students to unassigned for testing."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of students to switch. Default is 3.",
    )
    args = parser.parse_args()

    setup_logging()
    updated_app_ids = randomly_switch_allocated_students_to_unassigned(args.count)
    logger.info(
        "Switched %s student(s) from Allocated to Unassigned. application_ids=%s",
        len(updated_app_ids),
        updated_app_ids,
    )


if __name__ == "__main__":
    main()
