import json
import math
import logging

from integrations.beacon_client import beacon_client
from repositories.student_placement_events import create_student_placement_event
from repositories.students import (
    add_student_basic_overview,
    does_student_exist_basic_overview,
    update_student_status_basic_overview,
    update_student_status_full,
)

logger = logging.getLogger(__name__)


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


def update_simple_student_view(student) -> bool:
    requires_stage_2 = False
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
        # if student exists, confirm if the status is the same

        if current_status != status_in_db:
            # if status was unassigned but now is allocated, need to perform update just to ensure values did not change
            if status_in_db.lower() == "unassigned":
                logger.info(student)
                requires_stage_2 = True
            update_student_status_basic_overview(
                app_id=student_id, placement_status=current_status
            )
            update_student_status_full(
                app_id=student_id,
                placement_status=current_status,
                usahs_id=student.get("usaHsId"),
            )
            _record_placement_event(
                student_id=int(student_id),
                first_name=first_name,
                event_type="status_changed",
                placement_state="",
                coordinator_id=coordinator_id,
                manager_id=manager_id,
                status_from=status_in_db,
                status_to=current_status,
            )
        else:
            # status has not changed, no need to do anything additonal
            # update_student_status_basic_overview(
            #     app_id=student_id, placement_status=student.get("placementStatusName")
            # )
            pass
    else:
        # student does not exist, need to add student to the database
        add_student_basic_overview(student)
        if application_id is not None:
            _record_placement_event(
                student_id=application_id,
                first_name=first_name,
                event_type="student_added",
                placement_state=current_status,
                coordinator_id=coordinator_id,
                manager_id=manager_id,
                status_to=current_status,
            )
        requires_stage_2 = True

    return requires_stage_2


def get_updates_from_beacon(use_file_instead="") -> list:
    profiles_needing_stage_2 = []
    if use_file_instead != "":
        with open(use_file_instead, "r", encoding="utf-8") as source_file:
            json_data = json.load(source_file).get("results")

        # check if student already in table, if so then do they need to be updated?
        for student in json_data:
            requires_stage_2 = update_simple_student_view(student)
            if requires_stage_2 is True:
                profiles_needing_stage_2.append(student)

    else:
        PAGE_SIZE = 100

        json_data = {
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
            "page": 1,
            "pageSize": PAGE_SIZE,
            "gender": [],
        }

        response = beacon_client.post(
            "/beacon/Placement/searchwithcount", json=json_data
        )

        if response.status_code >= 400:  # ty:ignore[unsupported-operator]
            raise RuntimeError(
                f"Unable to fetch updates from Beacon. status_code={response.status_code}"
            )

        r_json = response.json()

        data = {"results": []}
        data["results"].extend(r_json.get("results", []))

        iterations_needed: int = math.ceil(r_json["count"] / PAGE_SIZE)

        for page_num in range(2, iterations_needed + 1):
            json_data["page"] = page_num
            response = beacon_client.post(
                "/beacon/Placement/searchwithcount", json=json_data
            )
            if response.status_code >= 400:  # ty:ignore[unsupported-operator]
                raise RuntimeError(
                    f"Unable to fetch Beacon page {page_num}. status_code={response.status_code}"
                )
            data["results"].extend(response.json().get("results", []))

        for student in data.get("results"):  # ty:ignore[not-iterable]
            if student["usaHsId"] == "":
                continue
            requires_stage_2 = update_simple_student_view(student)
            if requires_stage_2 is True:
                profiles_needing_stage_2.append(student)

    logger.info("Phase 1 update completed")
    logger.info(
        "Number of profiles needing phase 2 - %s", len(profiles_needing_stage_2)
    )
    # update the time so the last update time is visible to users
    return profiles_needing_stage_2
