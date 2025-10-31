import os

import requests
from dotenv import load_dotenv

load_dotenv()

def gen_auth_code():
    headers = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
}

    username: str = os.getenv("beacon_username", "")
    password: str = os.getenv("beacon_password", "")
    if username == "" or password == "":
        raise ValueError("Beacon Username/Password missing from environment")

    data = {
        "username": username,
        "password": password,
        "grant_type": "password",
        "scope": "offline_access",
        "resource": "https://api.ciee.org/beacon/",
    }

    response = requests.post(
        "https://api.ciee.org/beacon/authorization/token", 
        data=data, 
        headers=headers
    )

    # Auth code generated successfully
    if response.status_code < 400:
        pass
    else:
        print("Failure generating auth code, exiting.")
        return None

    access_token: str = "Bearer " + response.json()["access_token"]

    with open("bearer_token", "w") as f:
        f.write(access_token)

    return access_token