import sqlite3

from core.config import settings

DB_PATH = settings.database_path


def get_connection(
    *, row_factory: bool = False, detect_types: bool = False
) -> sqlite3.Connection:
    flags = sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES if detect_types else 0
    connection = (
        sqlite3.connect(DB_PATH, detect_types=flags)
        if flags
        else sqlite3.connect(DB_PATH)
    )
    if row_factory:
        connection.row_factory = sqlite3.Row
    return connection
