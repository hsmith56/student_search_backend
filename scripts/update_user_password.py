import argparse
import hashlib
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.logging_config import setup_logging
from repositories.admin import initialize_db
from repositories.base import get_connection

logger = logging.getLogger(__name__)


def update_user_password_by_username(*, username: str, password: str) -> bool:
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE users
        SET hashed_password = ?
        WHERE username = ?
        """,
        (hashed_password, username),
    )
    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Update a user's password in the users table by username. "
            "The provided plaintext password is hashed before storage."
        )
    )
    parser.add_argument(
        "username",
        type=str,
        help="Username whose password should be updated.",
    )
    parser.add_argument(
        "password",
        type=str,
        help="Plaintext password to hash and store.",
    )
    args = parser.parse_args()

    username = args.username.strip()
    if username == "":
        parser.error("username must not be empty")
    if args.password == "":
        parser.error("password must not be empty")

    setup_logging()
    initialize_db()
    updated = update_user_password_by_username(
        username=username, password=args.password
    )
    if not updated:
        logger.error("User not found for username=%s", username)
        raise SystemExit(1)

    logger.info("Updated password hash for username=%s", username)


if __name__ == "__main__":
    main()
