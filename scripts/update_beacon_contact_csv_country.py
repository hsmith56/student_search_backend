import argparse
import csv
import logging
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.logging_config import setup_logging
from integrations.beacon_client import beacon_client

logger = logging.getLogger(__name__)

DEFAULT_CSV = Path("temp/beacon_students_contact_information.csv")
DETAIL_ENDPOINT_TEMPLATE = "/beacon/participant/phi/application/{application_id}"
COUNTRY_FIELD = "country"


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return _as_str(value)
    return ""


def _fetch_country(application_id: str) -> str:
    response = beacon_client.get(
        DETAIL_ENDPOINT_TEMPLATE.format(application_id=application_id)
    )
    if response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(
            f"Beacon detail failed for application_id={application_id}. status_code={response.status_code}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(
            f"Beacon detail payload was not an object for application_id={application_id}"
        )
    return _first_value(
        data,
        (
            "residenceCountry",
            "residencecountry",
            "country",
            "birthcountry",
            "birthCountry",
        ),
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"CSV has no header: {path}")
                rows = [dict(row) for row in reader]
            logger.info("Read CSV using encoding=%s", encoding)
            return list(reader.fieldnames), rows
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise ValueError(f"Unable to read CSV: {path}")


def _write_csv_safe(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _fetch_countries(application_ids: list[str], workers: int) -> tuple[dict[str, str], int]:
    countries: dict[str, str] = {}
    failed = 0

    if workers <= 1:
        for index, application_id in enumerate(application_ids, start=1):
            try:
                countries[application_id] = _fetch_country(application_id)
            except Exception as exc:
                failed += 1
                logger.warning("Country fetch failed application_id=%s: %s", application_id, exc)
            if index % 100 == 0:
                logger.info("Country progress processed=%s failed=%s", index, failed)
        return countries, failed

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_country, application_id): application_id
            for application_id in application_ids
        }
        for index, future in enumerate(as_completed(futures), start=1):
            application_id = futures[future]
            try:
                countries[application_id] = future.result()
            except Exception as exc:
                failed += 1
                logger.warning("Country fetch failed application_id=%s: %s", application_id, exc)
            if index % 100 == 0:
                logger.info("Country progress processed=%s failed=%s", index, failed)
    return countries, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-time CSV updater: add country to Beacon contact_information export. "
            "Uses one Beacon detail call per unique application_id."
        )
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help="CSV to update in place. Default: temp/beacon_students_contact_information.csv",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path. Default: overwrite --csv.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent Beacon detail workers. Default: 8. Use 1 for lowest Beacon pressure.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip .bak copy when overwriting input CSV.",
    )
    args = parser.parse_args()

    setup_logging()

    csv_path = args.csv
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    fieldnames, rows = _read_csv(csv_path)
    if "application_id" not in fieldnames:
        raise ValueError("CSV must include application_id column")
    if COUNTRY_FIELD not in fieldnames:
        insert_at = fieldnames.index("application_id") if "application_id" in fieldnames else len(fieldnames)
        fieldnames.insert(insert_at, COUNTRY_FIELD)

    application_ids = sorted(
        {
            _as_str(row.get("application_id"))
            for row in rows
            if _as_str(row.get("application_id")) != ""
            and _as_str(row.get(COUNTRY_FIELD)) == ""
        }
    )
    logger.info(
        "Loaded rows=%s unique_country_lookups_needed=%s",
        len(rows),
        len(application_ids),
    )

    beacon_client._get_token()
    countries, failed = _fetch_countries(application_ids, workers=max(1, int(args.workers)))

    updated = 0
    for row in rows:
        application_id = _as_str(row.get("application_id"))
        if application_id == "" or _as_str(row.get(COUNTRY_FIELD)) != "":
            continue
        country = countries.get(application_id, "")
        if country != "":
            row[COUNTRY_FIELD] = country
            updated += 1

    out_path = args.out or csv_path
    if out_path == csv_path and not args.no_backup:
        backup_path = csv_path.with_suffix(csv_path.suffix + ".bak")
        shutil.copy2(csv_path, backup_path)
        logger.info("Backup written: %s", backup_path)

    _write_csv_safe(out_path, fieldnames, rows)
    missing = sum(1 for row in rows if _as_str(row.get(COUNTRY_FIELD)) == "")
    logger.info(
        "CSV country update complete out=%s updated=%s failed_lookups=%s missing_country=%s",
        out_path,
        updated,
        failed,
        missing,
    )


if __name__ == "__main__":
    main()
