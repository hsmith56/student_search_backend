import logging
import time

import requests
from requests import Response
from requests.exceptions import RequestException

from core.config import settings
from utils.beacon_auth import gen_auth_code

logger = logging.getLogger(__name__)


class BeaconClient:
    def __init__(self) -> None:
        self.base_url = settings.beacon_base_url
        self.timeout_seconds = settings.beacon_timeout_seconds
        self.max_retries = settings.beacon_max_retries
        self.backoff_seconds = settings.beacon_retry_backoff_seconds
        self.token_path = settings.bearer_token_path
        self.session = requests.Session()
        self._cached_token: str | None = None

    def _read_token_from_disk(self) -> str | None:
        try:
            with open(self.token_path, "r", encoding="utf-8") as token_file:
                token = token_file.read().strip()
                return token if token != "" else None
        except FileNotFoundError:
            return None

    def _get_token(self) -> str:
        if self._cached_token:
            return self._cached_token

        token = self._read_token_from_disk()
        if token is None:
            token = gen_auth_code()
        if token is None or token == "":
            raise RuntimeError("Unable to authenticate with beacon")
        self._cached_token = token
        return token

    def _refresh_token(self) -> str:
        token = gen_auth_code()
        if token is None or token == "":
            raise RuntimeError("Unable to refresh beacon auth token")
        self._cached_token = token
        return token

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(self, method: str, path: str, **kwargs) -> Response:
        url = self._build_url(path)
        headers = kwargs.pop("headers", {}) or {}
        token = self._get_token()

        attempt = 0
        while True:
            request_headers = dict(headers)
            request_headers["Authorization"] = token
            request_headers.setdefault("Accept", "application/json, text/plain, */*")

            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=request_headers,
                    timeout=self.timeout_seconds,
                    **kwargs,
                )
            except RequestException as exc:
                if attempt >= self.max_retries:
                    raise
                sleep_for = self.backoff_seconds * (2**attempt)
                logger.warning(
                    "Beacon request error, retrying in %ss: %s", sleep_for, exc
                )
                time.sleep(sleep_for)
                attempt += 1
                continue

            if response.status_code in (401, 403):
                if attempt >= self.max_retries:
                    return response
                token = self._refresh_token()
                sleep_for = self.backoff_seconds * (2**attempt)
                logger.warning(
                    "Beacon auth rejected (%s), retrying in %ss",
                    response.status_code,
                    sleep_for,
                )
                time.sleep(sleep_for)
                attempt += 1
                continue

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt >= self.max_retries:
                    return response
                sleep_for = self.backoff_seconds * (2**attempt)
                logger.warning(
                    "Beacon transient error %s, retrying in %ss",
                    response.status_code,
                    sleep_for,
                )
                time.sleep(sleep_for)
                attempt += 1
                continue

            return response

    def get(self, path: str, **kwargs) -> Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> Response:
        return self.request("POST", path, **kwargs)


beacon_client = BeaconClient()
