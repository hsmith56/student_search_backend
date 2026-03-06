import hashlib
import logging
import re
from functools import lru_cache
from typing import Any, Optional

from fastapi import Request, Response

try:
    from posthog import Posthog
except Exception:  # pragma: no cover - fallback for optional local installs
    Posthog = None  # type: ignore[assignment]

from core.config import settings

logger = logging.getLogger(__name__)

_FULL_STUDENT_PATH_REGEX = re.compile(r"^/students/full/[^/]+$")
_TRACKED_ROUTE_EVENTS = {
    ("POST", "/auth/login"): "auth_login_requested",
    ("POST", "/students/search"): "students_search_requested",
    ("GET", "/user/favorites"): "user_favorites_viewed",
    ("PATCH", "/user/favorites"): "user_favorite_added",
    ("DELETE", "/user/favorites"): "user_favorite_deleted",
}


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolve_event_name(method: str, path: str) -> Optional[str]:
    event_name = _TRACKED_ROUTE_EVENTS.get((method, path))
    if event_name is not None:
        return event_name

    if method == "GET" and _FULL_STUDENT_PATH_REGEX.fullmatch(path):
        return "student_full_profile_viewed"

    return None


@lru_cache(maxsize=1)
def _get_client() -> Optional[Any]:
    if Posthog is None:
        logger.warning(
            "PostHog analytics disabled because 'posthog' dependency is unavailable."
        )
        return None

    if settings.post_hog_api_key == "" or settings.post_hog_host == "":
        logger.info(
            "PostHog analytics disabled. Set POST_HOG_API_KEY and POST_HOG_HOST."
        )
        return None

    try:
        return Posthog(
            project_api_key=settings.post_hog_api_key,
            host=settings.post_hog_host,
        )
    except Exception:
        logger.exception("Failed to initialize PostHog client")
        return None


def _resolve_distinct_id(request: Request) -> str:
    session_id = request.cookies.get("session_id")
    if session_id:
        return f"session:{_hash_value(session_id)}"

    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        return f"refresh:{_hash_value(refresh_token)}"

    host = request.client.host if request.client else "unknown"
    return f"anonymous:{_hash_value(host)}"


def capture_tracked_route_event(request: Request, response: Response) -> None:
    event_name = _resolve_event_name(request.method.upper(), request.url.path)
    if event_name is None:
        return

    client = _get_client()
    if client is None:
        return

    properties = {
        "method": request.method.upper(),
        "path": request.url.path,
        "status_code": response.status_code,
    }

    if event_name == "student_full_profile_viewed":
        app_id = request.url.path.rsplit("/", maxsplit=1)[-1]
        properties["app_id"] = app_id

    try:
        client.capture(
            distinct_id=_resolve_distinct_id(request),
            event=event_name,
            properties=properties,
        )
    except Exception:
        logger.exception("Failed to send PostHog event")


def shutdown_posthog() -> None:
    client = _get_client()
    if client is None:
        return

    try:
        client.shutdown()
    except Exception:
        logger.exception("Failed to shutdown PostHog client")
