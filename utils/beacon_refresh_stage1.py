import json
import math

import requests

from utils.beacon_auth import gen_auth_code
from utils.db import (
    does_student_exist_basic_overview,
    update_student_status_basic_overview,
    add_student_basic_overview,
)


def update_simple_student_view(student) -> bool:
    requires_stage_2 = False
    student_id, status_in_db = does_student_exist_basic_overview(
        student.get("applicationId")
    )
    if student_id is not None:
        # if student exists, confirm if the status is the same
        if student.get("placementStatusName") != status_in_db:
            # if status was unassigned but now is allocated, need to perform update just to ensure values did not change
            if status_in_db.lower() == "unassigned":
                requires_stage_2 = True
            update_student_status_basic_overview(
                app_id=student_id, placement_status=student.get("placementStatusName")
            )
        else:
            # status has not changed, no need to do anything additonal
            pass
    else:
        # student does not exist, need to add student to the database
        add_student_basic_overview(student)
        requires_stage_2 = True
    
    return requires_stage_2


def get_updates_from_beacon(use_file_instead="") -> list:
    profiles_needing_stage_2 = []
    if use_file_instead != "":
        json_data = json.load(open(use_file_instead)).get("results")

        # check if student already in table, if so then do they need to be updated?
        for student in json_data:
            requires_stage_2 = update_simple_student_view(student)
            if requires_stage_2 is True:
                profiles_needing_stage_2.append(student)

    else:
        PAGE_SIZE = 100
        try:
            AUTH_TOKEN = open("bearer_token", "r").read()
        except FileNotFoundError:
            AUTH_TOKEN = gen_auth_code()

        if AUTH_TOKEN is None:
            raise Exception("Unable to authenticate to base system")

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": AUTH_TOKEN,
        }

        # TODO: perform some PING here to confirm auth code is valid

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

        response = requests.post(
            "https://api.ciee.org/beacon/Placement/searchwithcount",
            headers=headers,
            json=json_data,
        )

        if response.status_code >= 400:
            print("Bad authorization, generating new token.")
            AUTH_TOKEN = gen_auth_code()
            if AUTH_TOKEN is None:
                raise Exception("Unable to authenticate with beacon")
            headers["Authorization"] = AUTH_TOKEN
            response = requests.post(
                "https://api.ciee.org/beacon/Placement/searchwithcount",
                headers=headers,
                json=json_data,
            )

        r_json = response.json()

        data = {"results": []}
        data["results"].extend(r_json.get("results", []))

        iterations_needed: int = math.ceil(r_json["count"] / PAGE_SIZE)

        for page_num in range(2, iterations_needed + 1):
            json_data["page"] = page_num
            response = requests.post(
                "https://api.ciee.org/beacon/Placement/searchwithcount",
                headers=headers,
                json=json_data,
            )
            data["results"].extend(response.json().get("results", []))
        
        for student in data.get("results"):
            if student['usaHsId'] == "":
                continue
            requires_stage_2 = update_simple_student_view(student)
            if requires_stage_2 is True:
                profiles_needing_stage_2.append(student)
            

    print("Phase 1 update completed")
    print(f"Number of profiles needing phase 2 - {len(profiles_needing_stage_2)}")
    # update the time so the last update time is visible to users
    return profiles_needing_stage_2
    
