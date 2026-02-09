import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

DEFAULT_CORS_ORIGINS = (
    "https://localhost",
    "http://localhost",
    "https://hsmithtech.com",
    "https://www.hsmithtech.com",
    "*",
)


def _parse_csv(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None or raw.strip() == "":
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip() != "")
    return values if len(values) > 0 else default


def _to_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _resolve_path(raw: str | None, default: Path) -> str:
    value = Path(raw) if raw else default
    if not value.is_absolute():
        value = ROOT_DIR / value
    return str(value.resolve())


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "student-search-api")
        self.database_path = _resolve_path(
            os.getenv("DATABASE_PATH"), default=Path("user_auth.db")
        )
        self.bearer_token_path = _resolve_path(
            os.getenv("BEARER_TOKEN_PATH"), default=Path("bearer_token")
        )
        self.cors_origins = _parse_csv(
            os.getenv("CORS_ORIGINS"),
            default=DEFAULT_CORS_ORIGINS,
        )
        self.beacon_base_url = os.getenv(
            "BEACON_BASE_URL", "https://api.ciee.org"
        ).rstrip("/")
        self.beacon_threads = _to_int(os.getenv("BEACON_THREADS"), default=16)
        self.beacon_username = os.getenv("BEACON_USERNAME") or os.getenv(
            "beacon_username", ""
        )
        self.beacon_password = os.getenv("BEACON_PASSWORD") or os.getenv(
            "beacon_password", ""
        )


settings = Settings()
