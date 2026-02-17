from routers.auth import get_current_user
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.logging_config import setup_logging
from core.placement_notifications import placement_notification_hub
from repositories.admin import initialize_db
from routers import (
    admin,
    auth,
    feedback,
    misc,
    news_feed,
    notifications,
    placement_metrics,
    rpm,
    students,
    users,
)

setup_logging()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,  # ty:ignore[invalid-argument-type]
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router, dependencies=[Depends(get_current_user)])
app.include_router(students.router, dependencies=[Depends(get_current_user)])
app.include_router(misc.router, dependencies=[Depends(get_current_user)])
app.include_router(users.router, dependencies=[Depends(get_current_user)])
app.include_router(feedback.router, dependencies=[Depends(get_current_user)])
app.include_router(news_feed.router, dependencies=[Depends(get_current_user)])
app.include_router(
    placement_metrics.router, dependencies=[Depends(get_current_user)]
)
app.include_router(rpm.router, dependencies=[Depends(get_current_user)])
app.include_router(notifications.router)


@app.on_event("startup")
async def startup_init() -> None:
    initialize_db()
    await placement_notification_hub.start()


@app.on_event("shutdown")
async def shutdown_cleanup() -> None:
    await placement_notification_hub.stop()
