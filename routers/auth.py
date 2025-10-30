from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
import datetime
import hashlib
import uuid
from pydantic import BaseModel

from utils import db 

SESSION_COOKIE_NAME = "session_id"
sessions = {}  # still OK to keep in-memory sessions for simplicity
REFRESH_COOKIE_NAME = "refresh_token"
# TTLs in seconds
SESSION_TTL = 3600  # 1 hour
REFRESH_TTL = 60 * 60 * 24 * 7  # 7 days
refresh_tokens = {}

router = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(password: str):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain_password, hashed_password):
    return hash_password(plain_password) == hashed_password


def create_session(username: str, user_id: str, first_name: str) -> str:
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "username": username,
        "user_id": user_id,
        "first_name": first_name,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    return session_id


def create_refresh_token(user_id: str) -> str:
    token = str(uuid.uuid4())
    refresh_tokens[token] = {
        "user_id": user_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    return token


def get_current_user(
    response: Response,
    session_id: Optional[str] = Cookie(default=None),
    refresh_token: Optional[str] = Cookie(default=None),
):
    """Return current user; if session expired but a valid refresh token exists,
    issue a new session cookie transparently and return the user.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # Check existing session
    if session_id and session_id in sessions:
        session = sessions[session_id]
        age = (now - session["created_at"]).total_seconds()
        if age < SESSION_TTL:
            user_id = session["user_id"]
            user = db.read_user(user_id=user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found in database")
            return user
        else:
            # expired session; remove it and fall through to try refresh
            try:
                del sessions[session_id]
            except KeyError:
                pass

    # Try to refresh using refresh token
    if refresh_token and refresh_token in refresh_tokens:
        r = refresh_tokens[refresh_token]
        age = (now - r["created_at"]).total_seconds()
        if age < REFRESH_TTL:
            user_id = r["user_id"]
            user = db.read_user(user_id=user_id)
            if not user:
                # token refers to a missing user; remove token
                try:
                    del refresh_tokens[refresh_token]
                except KeyError:
                    pass
                raise HTTPException(status_code=404, detail="User not found in database")

            # create new session and set cookie
            new_session_id = create_session(user["username"], user["id"], user["first_name"])
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=new_session_id,
                httponly=True,
                secure=True,
                samesite="none",
                max_age=SESSION_TTL,
            )
            return user
        else:
            # refresh token expired; remove it
            try:
                del refresh_tokens[refresh_token]
            except KeyError:
                pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
    )


@router.post("/login")
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    print("HERE")
    user = db.read_user(username=form_data.username)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid username or password")

    if not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    session_id = create_session(user["username"], user["id"], user["first_name"])
    # set session cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=SESSION_TTL,
    )

    # create and set refresh token
    refresh = create_refresh_token(user["id"])
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TTL,
    )
    return {"message": "Logged in successfully"}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return full user profile from database"""
    user = {key: current_user[key] for key in current_user.keys()}
    return user


@router.post("/logout")
def logout(
    response: Response,
    session_id: Optional[str] = Cookie(default=None),
    refresh_token: Optional[str] = Cookie(default=None),
):
    # delete session server-side
    if session_id and session_id in sessions:
        try:
            del sessions[session_id]
        except KeyError:
            pass

    # delete refresh token server-side if provided
    if refresh_token and refresh_token in refresh_tokens:
        try:
            del refresh_tokens[refresh_token]
        except KeyError:
            pass

    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME)
    return {"message": "Logged out"}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    first_name: str
    code: str


@router.post("/register")
def register_user(user: CreateUserRequest):
    if (
        verify_password(
            plain_password=user.code,
            hashed_password="0d03fb3ebcf6dfc221af83f7bf5d58f0066876ee7ae7caf0d8fbdaa8a1453a74",
        )
        is False
    ):
        raise HTTPException(status_code=401, detail="Invalid signup code provided")

    existing = db.read_user(username=user.username)

    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    db.create_user(user.username, user.password, user.first_name, favorites=[])
    return {"message": f"User '{user.username}' created successfully"}
