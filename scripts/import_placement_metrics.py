import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.logging_config import setup_logging
from repositories.admin import initialize_db
from repositories.base import get_connection

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = ROOT_DIR / "placement_data.json"


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def _extract_row(result: dict[str, Any]) -> tuple[int, str | None, str | None, str]:
    app_id = int(result["app_id"])
    payload = result.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload is not a JSON object")

    placement_date_value = _normalize_text(payload.get("placementDate"))
    if placement_date_value is None:
        raise ValueError("placementDate is missing")

    return (
        app_id,
        _normalize_text(payload.get("city")),
        _normalize_text(payload.get("state")),
        placement_date_value,
    )


def import_placement_metrics(input_path: Path) -> tuple[int, int]:
    with open(input_path, "r", encoding="utf-8") as input_file:
        data = json.load(input_file)

    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError("placement_data.json is missing a valid 'results' list")

    upsert_sql = """
    INSERT INTO placement_metrics (app_id, city, state, placementDate)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(app_id) DO UPDATE SET
        city = excluded.city,
        state = excluded.state,
        placementDate = excluded.placementDate
    """

    imported = 0
    skipped = 0
    skip_examples: list[str] = []
    with get_connection() as connection:
        cursor = connection.cursor()
        for result in results:
            try:
                row = _extract_row(result)
            except Exception as exc:
                skipped += 1
                if len(skip_examples) < 5:
                    skip_examples.append(str(exc))
                continue
            cursor.execute(upsert_sql, row)
            imported += 1
        connection.commit()

    if skipped > 0:
        logger.warning("Skipped %s records during import", skipped)
        for index, example in enumerate(skip_examples, start=1):
            logger.warning("Skip example %s: %s", index, example)

    return imported, skipped


def main() -> None:
    setup_logging()
    initialize_db()

    input_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_INPUT_PATH
    logger.info("Importing placement metrics from %s", input_path)

    imported, skipped = import_placement_metrics(input_path)
    logger.info("placement_metrics import complete imported=%s skipped=%s", imported, skipped)


if __name__ == "__main__":
    main()
