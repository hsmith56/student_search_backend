import json
import math
import requests

from utils.beacon_auth import gen_auth_code
from utils.db import does_student_exist, update_student_status


def first_filter(data=None):
    data = json.load(open("response_json.json", "r"))

    # if student is already loaded into database then only need to check if status is different
    # otherwise treat student as not in db yet

    for student in data['results']:
        # Check if student in database
        student_id, status_in_db = does_student_exist(student.get('applicationId'))
        if student_id is not None:
            # if student exists, confirm if the status is the same
            if student.get('placementStatusName') != status_in_db:
                update_student_status(student_id, student.get('placementStatusName'))

        else:
            ...




def update_responses() -> None:

    
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

    with open("response_json.json", "w") as f:
        json.dump(data, f)

    # return data["results"]
    return None

