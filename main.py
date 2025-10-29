from routers.auth import get_current_user
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import misc, students, auth, users  # embeddings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost",
        "http://localhost",
        "https://hsmithtech.com",
        "https://www.hsmithtech.com",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(students.router, dependencies=[Depends(get_current_user)])
app.include_router(misc.router, dependencies=[Depends(get_current_user)])
app.include_router(users.router, dependencies=[Depends(get_current_user)])
