import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import settings
from integrations.beacon_client import BeaconClient
from utils.beacon_auth import gen_auth_code

PAGE_SIZE = 100

DEFAULT_STAGE1_PAYLOAD: dict[str, Any] = {
    "currentOnly": True,

    "statuses": [
        1,
        3,
        4,
        5,
        6,
        7,
        8,
        2,
        9,
        10,
        18,
        19,
    ],
    "states": [],
    "products": [223, 224],
    "orderBy": "ModifiedOn",
    "andBy": "",
    "ascending": False,
    "rds": [],
    "showDeleted": False,
    "appStatuses": [],
    "localCoordinators": [],
    "year": [],
    "agent": [],
    "pageSize": PAGE_SIZE,
    "page": 1,
    "gender": [],
}


def _truncate(value: str, max_chars: int = 500) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}... [truncated]"


def _print_json(title: str, data: dict[str, Any]) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(data, indent=2, default=str))


def _print_response(label: str, response) -> None:
    safe_headers = {
        "content-type": response.headers.get("Content-Type"),
        "date": response.headers.get("Date"),
        "server": response.headers.get("Server"),
        "x-request-id": response.headers.get("x-request-id"),
    }
    body_preview = _truncate(response.text or "")
    _print_json(
        label,
        {
            "status_code": response.status_code,
            "url": str(response.url),
            "headers": safe_headers,
            "body_preview": body_preview,
        },
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone Beacon connectivity/auth diagnostic."
    )
    parser.add_argument(
        "--mode",
        choices=["auth", "stage1", "all"],
        default="all",
        help="What to test. Default: all.",
    )
    parser.add_argument(
        "--payload-file",
        type=Path,
        default=None,
        help="Optional JSON file for /beacon/Placement/searchwithcount payload.",
    )
    parser.add_argument(
        "--application-id",
        type=int,
        default=None,
        help="Optional application id to test stage2-style endpoint (/participant/phi/application/{id}).",
    )
    parser.add_argument(
        "--debug-http",
        action="store_true",
        help="Enable debug logging for requests/urllib3.",
    )
    return parser.parse_args()


def _load_payload(payload_file: Path | None) -> dict[str, Any]:
    if payload_file is None:
        return dict(DEFAULT_STAGE1_PAYLOAD)
    with payload_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Payload JSON must be an object")
    return payload


def _validate_env() -> None:
    _print_json(
        "Config",
        {
            "beacon_base_url": settings.beacon_base_url,
            "beacon_timeout_seconds": settings.beacon_timeout_seconds,
            "beacon_max_retries": settings.beacon_max_retries,
            "beacon_retry_backoff_seconds": settings.beacon_retry_backoff_seconds,
            "bearer_token_path": settings.bearer_token_path,
            "beacon_username_present": settings.beacon_username != "",
            "beacon_password_present": settings.beacon_password != "",
        },
    )

    if settings.beacon_username == "" or settings.beacon_password == "":
        raise RuntimeError("Missing BEACON_USERNAME/beacon_username or BEACON_PASSWORD/beacon_password in environment")


def _configure_logging(debug_http: bool) -> None:
    level = logging.DEBUG if debug_http else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    if debug_http:
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("requests").setLevel(logging.DEBUG)


def run(mode: str, payload_file: Path | None, application_id: int | None) -> int:
    _validate_env()

    token = None
    if mode in {"auth", "all", "stage1"}:
        print("\n== Auth Test ==")
        started = time.perf_counter()
        token = gen_auth_code()
        elapsed = time.perf_counter() - started
        if token is None:
            raise RuntimeError("gen_auth_code() returned None")
        print(f"Token acquired in {elapsed:.2f}s")
        print(f"Bearer token written to: {settings.bearer_token_path}")

    if mode in {"stage1", "all"}:
        payload = _load_payload(payload_file)
        _print_json("Stage1 Payload", payload)

        client = BeaconClient()
        if token:
            client._cached_token = token

        print("\n== Stage1 Endpoint Test ==")
        started = time.perf_counter()
        response = client.post("/beacon/Placement/searchwithcount", json=payload)
        elapsed = time.perf_counter() - started
        _print_response("Stage1 Response", response)
        print(f"Elapsed: {elapsed:.2f}s")

        if response.status_code >= 400:
            print(
                "Stage1 probe returned an error. If status is 500, this likely indicates upstream Beacon or payload/product filter issues."
            )
            return 2

    if application_id is not None:
        client = BeaconClient()
        if token:
            client._cached_token = token

        print("\n== Stage2 Endpoint Probe ==")
        started = time.perf_counter()
        response = client.get(f"/beacon/participant/phi/application/{application_id}")
        elapsed = time.perf_counter() - started
        _print_response("Stage2 Probe Response", response)
        print(f"Elapsed: {elapsed:.2f}s")

        if response.status_code >= 400:
            return 3

    return 0


def main() -> None:
    args = _parse_args()
    _configure_logging(args.debug_http)
    try:
        exit_code = run(
            mode=args.mode,
            payload_file=args.payload_file,
            application_id=args.application_id,
        )
    except Exception as exc:
        print(f"\nERROR: {exc}")
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
