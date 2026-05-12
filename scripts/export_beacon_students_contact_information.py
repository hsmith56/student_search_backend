import argparse
import csv
import json
import logging
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import settings
from core.logging_config import setup_logging
from integrations.beacon_client import beacon_client

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 100
DEFAULT_THREADS = 8
DEFAULT_STATUSES = [
    1,   # Allocated
    3,   # On hold
    4,   # Placement Pending
    5,   # Placement - Review Needed
    6,   # Placed
    7,   # Placed - Accepted
    8,   # Placed - Closed
    10,  # Placed - Updated
    18,  # Unassigned
]
DEFAULT_PRODUCTS = [223, 224]

SEARCH_ENDPOINT = "/beacon/Placement/searchwithcount"
MAPPINGS_ENDPOINT_TEMPLATE = "/beacon/sections/standardtype/{application_id}"
CONTACT_ENDPOINT_TEMPLATE = "/beacon/Participant/contactInformation/section/{section_id}"

CSV_FIELDS = [
    "full_name",
    "first_name",
    "middle_name",
    "last_name",
    "home_address_city",
    "home_address_region",
    "home_address_post_code",
    "application_id",
    "participant_id",
    "beacon_id",
    "usa_hs_id",
    "atlas_id",
    "agency_id",
    "placement_status_id",
    "placement_status_name",
    "product_id",
    "product_name",
]


def _parse_int_csv(raw: str | None, default: list[int]) -> list[int]:
    if raw is None:
        return list(default)
    value = raw.strip()
    if value == "":
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip() != ""]


def _first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return ""


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_search_payload(page_size: int, statuses: list[int], products: list[int]) -> dict[str, Any]:
    return {
        "appStatuses": [],
        "statuses": statuses,
        "states": [],
        "products": products,
        "orderBy": "ModifiedOn",
        "andBy": "",
        "ascending": False,
        "rds": [],
        "showDeleted": False,
        "localCoordinators": [],
        "currentOnly": True,
        "year": [],
        "agent": [],
        "pageSize": page_size,
        "gender": [],
    }


def _fetch_search_page(search_payload: dict[str, Any], page: int) -> tuple[list[dict[str, Any]], int | None]:
    payload = dict(search_payload)
    payload["page"] = page
    response = beacon_client.post(SEARCH_ENDPOINT, json=payload)
    if response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(f"Beacon search page {page} failed. status_code={response.status_code}")

    data = response.json()
    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError(f"Beacon search page {page} results was not a list")
    count = data.get("count")
    return results, int(count) if count is not None else None


def _fetch_all_search_students(search_payload: dict[str, Any], page_workers: int) -> list[dict[str, Any]]:
    first_page, total_count = _fetch_search_page(search_payload, page=1)
    if total_count is None:
        logger.info("Fetched page 1. total_count missing. Returning first page only.")
        return first_page

    page_size = int(search_payload["pageSize"])
    total_pages = math.ceil(total_count / page_size)
    logger.info("Beacon search total_count=%s total_pages=%s", total_count, total_pages)
    if total_pages <= 1:
        return first_page

    pages: dict[int, list[dict[str, Any]]] = {1: first_page}
    worker_count = max(1, min(page_workers, total_pages - 1))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(_fetch_search_page, search_payload, page): page
            for page in range(2, total_pages + 1)
        }
        for future in as_completed(futures):
            page = futures[future]
            page_rows, _ = future.result()
            pages[page] = page_rows
            logger.info("Fetched Beacon search page %s/%s rows=%s", page, total_pages, len(page_rows))

    students: list[dict[str, Any]] = []
    for page in range(1, total_pages + 1):
        students.extend(pages.get(page, []))
    return students


def _fetch_category_mappings(application_id: Any) -> dict[str, Any]:
    if application_id in (None, ""):
        return {}
    response = beacon_client.get(MAPPINGS_ENDPOINT_TEMPLATE.format(application_id=application_id))
    if response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(
            f"Beacon section mappings failed for application_id={application_id}. status_code={response.status_code}"
        )
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"Beacon section mappings payload was not a list for application_id={application_id}")
    return {
        item.get("sectionName"): item.get("id")
        for item in data
        if isinstance(item, dict)
    }


def _fetch_contact_information(section_id: Any, endpoint_template: str) -> dict[str, Any]:
    if section_id in (None, ""):
        return {}
    response = beacon_client.get(endpoint_template.format(section_id=section_id))
    if response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(
            f"Beacon contactInformation failed for section_id={section_id}. status_code={response.status_code}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Beacon contactInformation payload was not an object for section_id={section_id}")
    return data


def _merge_contact_information(student: dict[str, Any], endpoint_template: str) -> dict[str, Any]:
    application_id = _first_value(student, ("applicationId", "applicationid"))
    mappings = _fetch_category_mappings(application_id)
    contact_section_id = mappings.get("contactInformation")
    contact_info = _fetch_contact_information(contact_section_id, endpoint_template)

    merged = dict(student)
    merged.update(
        {
            "homeAddressCity": contact_info.get("homeAddressCity", ""),
            "homeAddressRegion": contact_info.get("homeAddressRegion", ""),
            "homeAddressPostCode": contact_info.get("homeAddressPostCode", ""),
        }
    )
    return merged


def _student_to_export_row(student: dict[str, Any]) -> dict[str, str]:
    first_name = _as_str(_first_value(student, ("paxNameFirst", "namefirst", "nameFirst", "firstname"))).title()
    middle_name = _as_str(_first_value(student, ("namemiddle", "nameMiddle", "middleName"))).title()
    last_name = _as_str(_first_value(student, ("paxNameLast", "namelast", "nameLast", "lastname"))).title()
    full_name = " ".join(part for part in [first_name, middle_name, last_name] if part != "")

    usa_hs_id = _first_value(student, ("usaHsId", "usahsId", "usahsid", "atlasId"))

    return {
        "full_name": full_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "home_address_city": _as_str(_first_value(student, ("homeAddressCity", "home_address_city"))).title(),
        "home_address_region": _as_str(_first_value(student, ("homeAddressRegion", "home_address_region"))).title(),
        "home_address_post_code": _as_str(_first_value(student, ("homeAddressPostCode", "home_address_post_code"))),
        "application_id": _as_str(_first_value(student, ("applicationId", "applicationid", "app_id"))),
        "participant_id": _as_str(_first_value(student, ("participantId", "participantid", "pax_id"))),
        "beacon_id": _as_str(_first_value(student, ("id", "student_id"))),
        "usa_hs_id": _as_str(usa_hs_id),
        "atlas_id": _as_str(_first_value(student, ("atlasId", "atlasid"))),
        "agency_id": _as_str(_first_value(student, ("agencyId", "agencyid"))),
        "placement_status_id": _as_str(_first_value(student, ("placementStatusId", "placementstatusid"))),
        "placement_status_name": _as_str(_first_value(student, ("placementStatusName", "placementstatusname"))),
        "product_id": _as_str(_first_value(student, ("productid", "productId"))),
        "product_name": _as_str(_first_value(student, ("productName", "productname"))),
    }


def _hydrate_contact_information(
    students: list[dict[str, Any]],
    contact_workers: int,
    endpoint_template: str,
) -> tuple[list[dict[str, Any]], int, int]:
    logger.info(
        "Students loaded=%s contact_calls_needed=%s mapping_calls_needed=%s",
        len(students),
        len(students),
        len(students),
    )

    merged_by_index: dict[int, dict[str, Any]] = {}
    failed = 0

    if contact_workers <= 1:
        for index, student in enumerate(students):
            try:
                merged_by_index[index] = _merge_contact_information(student, endpoint_template)
            except Exception as exc:
                failed += 1
                merged_by_index[index] = student
                logger.warning(
                    "Contact fetch failed application_id=%s: %s",
                    _first_value(student, ("applicationId", "applicationid")),
                    exc,
                )
    else:
        with ThreadPoolExecutor(max_workers=contact_workers) as pool:
            futures = {
                pool.submit(_merge_contact_information, student, endpoint_template): index
                for index, student in enumerate(students)
            }
            for processed, future in enumerate(as_completed(futures), start=1):
                index = futures[future]
                original = students[index]
                try:
                    merged_by_index[index] = future.result()
                except Exception as exc:
                    failed += 1
                    merged_by_index[index] = original
                    logger.warning(
                        "Contact fetch failed application_id=%s: %s",
                        _first_value(original, ("applicationId", "applicationid")),
                        exc,
                    )
                if processed % 100 == 0:
                    logger.info("Contact progress processed=%s failed=%s", processed, failed)

    merged_students = [merged_by_index[index] for index in range(len(students))]
    attempted = len(students)
    return merged_students, attempted, failed


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-time Beacon export: student names, IDs, contact city/region/post code. "
            "Uses paged search + contactInformation section per student."
        )
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("temp/beacon_students_contact_information.csv"),
        help="CSV output path. Default: temp/beacon_students_contact_information.csv",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Beacon search page size. Default: 100.",
    )
    parser.add_argument(
        "--page-workers",
        type=int,
        default=settings.beacon_stage1_page_fetch_workers,
        help="Concurrent page fetch workers. Default: BEACON_STAGE1_PAGE_FETCH_WORKERS.",
    )
    parser.add_argument(
        "--contact-workers",
        type=int,
        default=DEFAULT_THREADS,
        help="Concurrent contactInformation fetch workers. Default: 8. Use 1 for lowest Beacon pressure.",
    )
    parser.add_argument(
        "--statuses",
        type=str,
        default=",".join(str(status) for status in DEFAULT_STATUSES),
        help="Comma-separated Beacon placement status IDs. Empty string means all statuses.",
    )
    parser.add_argument(
        "--products",
        type=str,
        default=",".join(str(product) for product in DEFAULT_PRODUCTS),
        help="Comma-separated Beacon product IDs. Empty string means all products.",
    )
    parser.add_argument(
        "--contact-endpoint-template",
        type=str,
        default=CONTACT_ENDPOINT_TEMPLATE,
        help="Beacon contactInformation endpoint template. Must include {section_id}.",
    )
    args = parser.parse_args()

    if "{section_id}" not in args.contact_endpoint_template:
        parser.error("--contact-endpoint-template must include {section_id}")

    setup_logging()
    beacon_client._get_token()

    page_size = max(1, int(args.page_size))
    page_workers = max(1, int(args.page_workers))
    contact_workers = max(1, int(args.contact_workers))
    statuses = _parse_int_csv(args.statuses, DEFAULT_STATUSES)
    products = _parse_int_csv(args.products, DEFAULT_PRODUCTS)

    logger.info(
        "Starting Beacon contactInformation export out=%s statuses=%s products=%s page_size=%s page_workers=%s contact_workers=%s",
        args.out,
        statuses,
        products,
        page_size,
        page_workers,
        contact_workers,
    )

    search_payload = _build_search_payload(
        page_size=page_size,
        statuses=statuses,
        products=products,
    )
    students = _fetch_all_search_students(search_payload, page_workers=page_workers)
    students, contact_attempted, contact_failed = _hydrate_contact_information(
        students,
        contact_workers=contact_workers,
        endpoint_template=args.contact_endpoint_template,
    )

    rows = [_student_to_export_row(student) for student in students]
    _write_csv(args.out, rows)
    if args.json_out is not None:
        _write_json(args.json_out, rows)

    missing_city = sum(1 for row in rows if row["home_address_city"] == "")
    logger.info(
        "Export complete rows=%s csv=%s json=%s contact_attempted=%s contact_failed=%s missing_city=%s",
        len(rows),
        args.out,
        args.json_out,
        contact_attempted,
        contact_failed,
        missing_city,
    )


if __name__ == "__main__":
    main()
