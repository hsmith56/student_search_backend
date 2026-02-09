from routers.auth import get_current_user
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from routers import misc, students, auth, users, feedback  # embeddings
from utils import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,  # ty:ignore[invalid-argument-type]
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(students.router, dependencies=[Depends(get_current_user)])
app.include_router(misc.router, dependencies=[Depends(get_current_user)])
app.include_router(users.router, dependencies=[Depends(get_current_user)])
app.include_router(feedback.router, dependencies=[Depends(get_current_user)])


@app.on_event("startup")
def startup_init() -> None:
    db.initialize_db()
    db.update_time()
