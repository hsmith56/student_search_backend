import os
from pathlib import Path
from urllib.parse import urlparse

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


def _normalize_domain(raw: str | None) -> str:
    if raw is None or raw.strip() == "":
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path).strip().strip("/")
    return host


def _resolve_cors_origins(
    environment: str, raw_cors_origins: str | None, domain: str
) -> tuple[str, ...]:
    if environment != "production":
        return _parse_csv(raw_cors_origins, default=DEFAULT_CORS_ORIGINS)
    if domain == "":
        raise ValueError("DOMAIN must be set when ENVIRONMENT=production")
    return (
        f"http://{domain}",
        f"https://{domain}",
    )


def _to_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _resolve_path(raw: str | None, default: Path) -> str:
    value = Path(raw) if raw else default
    if not value.is_absolute():
        value = ROOT_DIR / value
    return str(value.resolve())


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "student-search-api")
        self.environment = os.getenv("ENVIRONMENT", "development").strip().lower()
        self.domain = _normalize_domain(os.getenv("DOMAIN"))
        self.database_path = _resolve_path(
            os.getenv("DATABASE_PATH"), default=Path("user_auth.db")
        )
        self.bearer_token_path = _resolve_path(
            os.getenv("BEARER_TOKEN_PATH"), default=Path("bearer_token")
        )
        self.cors_origins = _resolve_cors_origins(
            environment=self.environment,
            raw_cors_origins=os.getenv("CORS_ORIGINS"),
            domain=self.domain,
        )
        self.beacon_base_url = os.getenv(
            "BEACON_BASE_URL", "https://api.ciee.org"
        ).rstrip("/")
        self.beacon_threads = _to_int(os.getenv("BEACON_THREADS"), default=16)
        self.beacon_timeout_seconds = _to_int(
            os.getenv("BEACON_TIMEOUT_SECONDS"), default=30
        )
        self.beacon_max_retries = _to_int(os.getenv("BEACON_MAX_RETRIES"), default=3)
        self.beacon_retry_backoff_seconds = _to_int(
            os.getenv("BEACON_RETRY_BACKOFF_SECONDS"), default=1
        )
        self.beacon_stage1_page_fetch_workers = max(
            1,
            _to_int(os.getenv("BEACON_STAGE1_PAGE_FETCH_WORKERS"), default=4),
        )
        self.beacon_stage1_db_read_workers = max(
            1,
            _to_int(os.getenv("BEACON_STAGE1_DB_READ_WORKERS"), default=16),
        )
        self.log_dir = _resolve_path(os.getenv("LOG_DIR"), default=Path("log"))
        self.log_file_name = os.getenv("LOG_FILE_NAME", "app.log")
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_max_bytes = _to_int(os.getenv("LOG_MAX_BYTES"), default=5_242_880)
        self.log_backup_count = _to_int(os.getenv("LOG_BACKUP_COUNT"), default=5)
        self.log_to_console = _to_bool(os.getenv("LOG_TO_CONSOLE"), default=True)
        self.beacon_username = os.getenv("BEACON_USERNAME") or os.getenv(
            "beacon_username", ""
        )
        self.beacon_password = os.getenv("BEACON_PASSWORD") or os.getenv(
            "beacon_password", ""
        )
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = _to_int(os.getenv("SMTP_PORT"), default=465)
        self.smtp_timeout_seconds = _to_int(
            os.getenv("SMTP_TIMEOUT_SECONDS"), default=30
        )
        self.signup_invite_url = os.getenv(
            "SIGNUP_INVITE_URL", "https://www.hsmithdev.xyz/login"
        )
        self.rpm_signup_code = os.getenv("RPM_SIGNUP_CODE", "")
        self.lc_signup_code = os.getenv("LC_SIGNUP_CODE", "")
        self.post_hog_api_key = os.getenv("POST_HOG_API_KEY", "").strip()
        self.post_hog_host = os.getenv("POST_HOG_HOST", "").strip().rstrip("/")


settings = Settings()
