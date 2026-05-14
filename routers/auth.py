from typing import Any, Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
import datetime
import hashlib
import uuid
from pydantic import BaseModel

from repositories.users import (
    complete_signup_registration,
    get_pending_user_by_signup_code,
    read_user,
    update_user_password_by_id,
)

SESSION_COOKIE_NAME = "session_id"
sessions = {}  # still OK to keep in-memory sessions for simplicity
REFRESH_COOKIE_NAME = "refresh_token"

SESSION_TTL = 3600  # 1 hour
REFRESH_TTL = 60 * 60 * 24 * 7  # 7 days
refresh_tokens = {}

router: APIRouter = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(password: str) -> str:
    return hashlib.sha256(string=password.encode(encoding="utf-8")).hexdigest()


def verify_password(plain_password, hashed_password) -> Any:
    return hash_password(password=plain_password) == hashed_password


def create_session(username: str, user_id: str, first_name: str) -> str:
    session_id: str = str(uuid.uuid4())
    sessions[session_id] = {
        "username": username,
        "user_id": user_id,
        "first_name": first_name,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
    }
    return session_id


def create_refresh_token(user_id: str) -> str:
    token = str(uuid.uuid4())
    refresh_tokens[token] = {
        "user_id": user_id,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc),
    }
    return token


def _authenticate_from_cookie_values(
    *,
    session_id: Optional[str],
    refresh_token: Optional[str],
    issue_new_session_on_refresh: bool,
) -> tuple[Any, str | None]:
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    # Check existing session
    if session_id and session_id in sessions:
        session = sessions[session_id]
        age = (now - session["created_at"]).total_seconds()
        if age < SESSION_TTL:
            user_id = session["user_id"]
            user = read_user(user_id=user_id)
            if not user:
                raise HTTPException(
                    status_code=404, detail="User not found in database"
                )
            return user, None

        # Expired session; remove it and fall through to try refresh.
        try:
            del sessions[session_id]
        except KeyError:
            pass

    # Try to refresh using refresh token.
    if refresh_token and refresh_token in refresh_tokens:
        r = refresh_tokens[refresh_token]
        age = (now - r["created_at"]).total_seconds()
        if age < REFRESH_TTL:
            user_id = r["user_id"]
            user = read_user(user_id=user_id)
            if not user:
                try:
                    del refresh_tokens[refresh_token]
                except KeyError:
                    pass
                raise HTTPException(
                    status_code=404, detail="User not found in database"
                )

            if issue_new_session_on_refresh:
                new_session_id = create_session(
                    username=user["username"],
                    user_id=user["id"],
                    first_name=user["first_name"],
                )
                return user, new_session_id
            return user, None

        # Refresh token expired; remove it.
        try:
            del refresh_tokens[refresh_token]
        except KeyError:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
    )


def get_current_user_for_websocket(
    *, session_id: Optional[str], refresh_token: Optional[str]
):
    user, _ = _authenticate_from_cookie_values(
        session_id=session_id,
        refresh_token=refresh_token,
        issue_new_session_on_refresh=False,
    )
    return user


def get_current_user(
    response: Response,
    session_id: Optional[str] = Cookie(default=None),
    refresh_token: Optional[str] = Cookie(default=None),
):
    """Return current user; if session expired but a valid refresh token exists,
    issue a new session cookie transparently and return the user.
    """
    user, new_session_id = _authenticate_from_cookie_values(
        session_id=session_id,
        refresh_token=refresh_token,
        issue_new_session_on_refresh=True,
    )
    if new_session_id:
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=new_session_id,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=SESSION_TTL,
        )
    return user


def _require_director_rpm_or_admin(current_user: dict) -> None:
    if current_user["account_type"] not in {"admin", "director", "rpm"}:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post(path="/login")
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = read_user(username=form_data.username)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid username or password")

    if not verify_password(
        plain_password=form_data.password, hashed_password=user["hashed_password"]
    ):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    session_id: str = create_session(
        username=user["username"], user_id=user["id"], first_name=user["first_name"]
    )
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
    refresh: str = create_refresh_token(user_id=user["id"])
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TTL,
    )
    return {"message": "Logged in successfully"}


@router.get(path="/me")
def me(current_user: dict = Depends(dependency=get_current_user)):
    """Return full user profile from database"""
    user = {key: current_user[key] for key in current_user.keys()}
    return user


@router.post(path="/logout")
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

    response.delete_cookie(key=SESSION_COOKIE_NAME)
    response.delete_cookie(key=REFRESH_COOKIE_NAME)
    return {"message": "Logged out"}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    first_name: str
    signup_code: str


class ChangePasswordRequest(BaseModel):
    new_password: str


class ResetUserPasswordRequest(BaseModel):
    temp_password: str
    user_id: str


@router.post(path="/change_password")
def change_password(
    payload: ChangePasswordRequest, current_user: dict = Depends(dependency=get_current_user)
):
    updated = update_user_password_by_id(
        user_id=current_user["id"],
        hashed_password=hash_password(password=payload.new_password),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found in database")
    return {"message": "Password changed successfully"}


@router.post(path="/reset_password")
def reset_password(
    payload: ResetUserPasswordRequest, current_user: dict = Depends(dependency=get_current_user)
):
    _require_director_rpm_or_admin(current_user=current_user)

    target_user = read_user(user_id=payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Target user not found")

    updated = update_user_password_by_id(
        user_id=payload.user_id,
        hashed_password=hash_password(password=payload.temp_password),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Target user not found")

    return {"message": "Temporary password reset successfully"}


@router.post(path="/register")
def register_user(user: CreateUserRequest):
    existing = read_user(username=user.username)

    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    signup = get_pending_user_by_signup_code(signup_code=user.signup_code)
    if signup is None:
        raise HTTPException(status_code=401, detail="Invalid signup code provided")

    try:
        completed = complete_signup_registration(
            user_id=str(signup["id"]),
            username=user.username,
            password=user.password,
            first_name=user.first_name,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to complete registration: {exc}"
        )

    if completed is False:
        raise HTTPException(status_code=401, detail="Invalid signup code provided")

    created_user = read_user(user_id=str(signup["id"]))
    if created_user is None:
        raise HTTPException(status_code=500, detail="Failed to create user")

    return {"message": f"User '{user.username}' created successfully"}
