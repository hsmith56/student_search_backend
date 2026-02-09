import requests
import logging
from core.config import settings

logger = logging.getLogger(__name__)


def gen_auth_code():
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    username: str = settings.beacon_username
    password: str = settings.beacon_password
    if username == "" or password == "":
        raise ValueError("Beacon Username/Password missing from environment")

    data = {
        "username": username,
        "password": password,
        "grant_type": "password",
        "scope": "offline_access",
        "resource": f"{settings.beacon_base_url}/beacon/",
    }

    response = requests.post(
        f"{settings.beacon_base_url}/beacon/authorization/token",
        data=data,
        headers=headers,
    )

    # Auth code generated successfully
    if response.status_code < 400:
        pass
    else:
        logger.error("Failure generating auth code, exiting.")
        return None

    access_token: str = "Bearer " + response.json()["access_token"]

    with open(settings.bearer_token_path, "w", encoding="utf-8") as f:
        f.write(access_token)

    return access_token
