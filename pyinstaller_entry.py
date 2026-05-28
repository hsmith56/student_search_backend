import os
import sys
from pathlib import Path

import uvicorn

from main import app


def bundled_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


if __name__ == "__main__":
    os.environ.setdefault("DATABASE_PATH", str(bundled_path("user_auth.db")))
    os.environ.setdefault("LOG_DIR", str(Path.home() / ".student-search" / "log"))

    port = int(os.environ.get("PORT", "8000"))

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        loop="asyncio",
        http="h11",
        ws="websockets",
    )
