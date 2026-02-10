import json
import math
import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.config import settings
from integrations.beacon_client import beacon_client
from repositories.student_placement_events import create_student_placement_event
from repositories.students import (
    add_student_basic_overview,
    does_student_exist_basic_overview,
    update_student_status_basic_overview,
    update_student_status_full,
)

logger = logging.getLogger(__name__)


@dataclass
class StudentWritePlan:
    student: dict
    is_new_student: bool
    app_id: int | None
    placement_status: str | None
    usahs_id: str
    event: dict | None
    requires_stage_2: bool


def _fetch_search_page(search_payload: dict, page_num: int) -> list[dict]:
    page_payload = dict(search_payload)
    page_payload["page"] = page_num
    response = beacon_client.post(
        "/beacon/Placement/searchwithcount", json=page_payload
    )
    if response.status_code >= 400:  # ty:ignore[unsupported-operator]
        raise RuntimeError(
            f"Unable to fetch Beacon page {page_num}. status_code={response.status_code}"
        )
    return response.json().get("results", [])


def _first_int(student: dict, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = student.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _record_placement_event(**event) -> None:
    try:
        create_student_placement_event(**event)
    except Exception as exc:
        logger.warning(
            "Unable to store placement event for student_id=%s: %s",
            event.get("student_id"),
            exc,
        )


def _build_student_write_plan(student: dict) -> StudentWritePlan | None:
    current_status = student.get("placementStatusName")
    first_name = student.get("paxNameFirst")
    application_id = _first_int(student, ("applicationId",))
    coordinator_id = _first_int(
        student, ("localCoordinatorId", "coordinatorId", "lcId")
    )
    manager_id = _first_int(
        student, ("managerId", "regionalManagerId", "placementManagerId")
    )

    student_id, status_in_db = does_student_exist_basic_overview(
        student.get("applicationId")
    )
    if student_id is not None:
        if current_status != status_in_db:
            requires_stage_2 = status_in_db.lower() == "unassigned"
            if requires_stage_2:
                logger.info(student)
            return StudentWritePlan(
                student=student,
                is_new_student=False,
                app_id=int(student_id),
                placement_status=current_status,
                usahs_id=student.get("usaHsId", ""),
                event={
                    "student_id": int(student_id),
                    "first_name": first_name,
                    "event_type": "status_changed",
                    "placement_state": "",
                    "coordinator_id": coordinator_id,
                    "manager_id": manager_id,
                    "status_from": status_in_db,
                    "status_to": current_status,
                },
                requires_stage_2=requires_stage_2,
            )
        return None

    event: dict | None = None
    if application_id is not None:
        event = {
            "student_id": application_id,
            "first_name": first_name,
            "event_type": "student_added",
            "placement_state": current_status,
            "coordinator_id": coordinator_id,
            "manager_id": manager_id,
            "status_to": current_status,
        }
    return StudentWritePlan(
        student=student,
        is_new_student=True,
        app_id=application_id,
        placement_status=current_status,
        usahs_id=student.get("usaHsId", ""),
        event=event,
        requires_stage_2=True,
    )


def _submit_students_for_read_planning(
    students: list[dict],
    read_pool: ThreadPoolExecutor,
    planning_futures: dict,
    next_index: int,
) -> int:
    for student in students:
        if student.get("usaHsId", "") == "":
            continue
        future = read_pool.submit(_build_student_write_plan, student)
        planning_futures[future] = next_index
        next_index += 1
    return next_index


def _apply_write_plans(write_plans: list[StudentWritePlan]) -> None:
    for plan in write_plans:
        if plan.is_new_student:
            add_student_basic_overview(plan.student)
        else:
            if plan.app_id is None:
                continue
            update_student_status_basic_overview(
                app_id=plan.app_id,
                placement_status=plan.placement_status,  # ty:ignore[invalid-argument-type]
            )
            update_student_status_full(
                app_id=plan.app_id,
                placement_status=plan.placement_status,  # ty:ignore[invalid-argument-type]
                usahs_id=plan.usahs_id,
            )

        if plan.event is not None:
            _record_placement_event(**plan.event)


def get_updates_from_beacon(use_file_instead="") -> list:
    MAX_PAGE_FETCH_WORKERS = settings.beacon_stage1_page_fetch_workers
    MAX_DB_READ_WORKERS = settings.beacon_stage1_db_read_workers
    profiles_needing_stage_2 = []
    ordered_write_plans: dict[int, StudentWritePlan] = {}

    with ThreadPoolExecutor(max_workers=MAX_DB_READ_WORKERS) as read_pool:
        planning_futures: dict = {}
        next_index = 0

        if use_file_instead != "":
            with open(use_file_instead, "r", encoding="utf-8") as source_file:
                json_data = json.load(source_file).get("results", [])
            next_index = _submit_students_for_read_planning(
                json_data, read_pool, planning_futures, next_index
            )
        else:
            PAGE_SIZE = 100
            search_payload = {
                "statuses": [
                    1,  # Allocated
                    4,  # Placement Pending
                    5,  # Placement - Review Needed
                    6,  # Placed
                    7,  # Placed - Accepted
                    8,  # Placed - Closed
                    10,  # Placed - Updated
                    18,  # unassigned
                ],
                "states": [],
                "products": [
                    223,  # 2025 aug 5  month
                    224,  # 2025 aug 10 month
                    225,  # 2025 jan 10 month
                    226,  # 2025 jan 5  month
                ],
                "orderBy": "ModifiedOn",
                "andBy": "",
                "ascending": False,
                "rds": [],
                "showDeleted": False,
                "localCoordinators": [],
                # "availableForPlacement": True,
                "year": [],
                "agent": [],
                "pageSize": PAGE_SIZE,
                "gender": [],
            }

            response = beacon_client.post(
                "/beacon/Placement/searchwithcount", json={**search_payload, "page": 1}
            )

            if response.status_code >= 400:  # ty:ignore[unsupported-operator]
                raise RuntimeError(
                    f"Unable to fetch updates from Beacon. status_code={response.status_code}"
                )

            r_json = response.json()
            next_index = _submit_students_for_read_planning(
                r_json.get("results", []),
                read_pool,
                planning_futures,
                next_index,
            )

            iterations_needed: int = math.ceil(r_json["count"] / PAGE_SIZE)
            if iterations_needed > 1:
                worker_count = min(MAX_PAGE_FETCH_WORKERS, iterations_needed - 1)
                with ThreadPoolExecutor(max_workers=worker_count) as page_pool:
                    page_futures = [
                        page_pool.submit(_fetch_search_page, search_payload, page_num)
                        for page_num in range(2, iterations_needed + 1)
                    ]
                    for future in as_completed(page_futures):
                        page_students = future.result()
                        next_index = _submit_students_for_read_planning(
                            page_students,
                            read_pool,
                            planning_futures,
                            next_index,
                        )

        for future in as_completed(planning_futures):
            write_plan = future.result()
            if write_plan is None:
                continue
            ordered_write_plans[planning_futures[future]] = write_plan

    sorted_indexes = sorted(ordered_write_plans)
    write_plans = [ordered_write_plans[index] for index in sorted_indexes]
    _apply_write_plans(write_plans)

    for plan in write_plans:
        if plan.requires_stage_2 is True:
            profiles_needing_stage_2.append(plan.student)

    logger.info("Phase 1 update completed")
    logger.info(
        "Number of profiles needing phase 2 - %s", len(profiles_needing_stage_2)
    )
    # update the time so the last update time is visible to users
    return profiles_needing_stage_2
