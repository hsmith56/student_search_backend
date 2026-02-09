import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.logging_config import setup_logging
from repositories.student_placement_events import create_unassigned_to_allocated_event

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Insert one news feed event (Unassigned -> Allocated). "
            "When the API notifier is running, this event will be broadcast over "
            "/notifications/ws/placements."
        )
    )
    parser.add_argument(
        "--student-id",
        type=int,
        required=True,
        help="Student application id for the feed event.",
    )
    parser.add_argument(
        "--coordinator-id",
        type=int,
        default=None,
        help="Optional coordinator id.",
    )
    parser.add_argument(
        "--manager-id",
        type=int,
        default=None,
        help="Optional manager id.",
    )
    parser.add_argument(
        "--event-at",
        type=str,
        default=None,
        help="Optional ISO timestamp override (default: current US/Eastern time).",
    )
    args = parser.parse_args()

    setup_logging()
    event_id = create_unassigned_to_allocated_event(
        student_id=args.student_id,
        coordinator_id=args.coordinator_id,
        manager_id=args.manager_id,
        event_at=args.event_at,
    )
    logger.info(
        "Added news feed event. event_id=%s student_id=%s status_from=Unassigned status_to=Allocated",
        event_id,
        args.student_id,
    )


if __name__ == "__main__":
    main()
