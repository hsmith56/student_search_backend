from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
import datetime
import hashlib
import uuid
from pydantic import BaseModel

from utils import db  # ✅ now using your db helpers

SESSION_COOKIE_NAME = "session_id"
sessions = {}  # still OK to keep in-memory sessions for simplicity

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

def get_current_user(session_id: Optional[str] = Cookie(default=None)):
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = sessions[session_id]["user_id"]
    user = db.read_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found in database")
    return user  

@router.post("/login")
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.read_user(username=form_data.username)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid username or password")

    if not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    session_id = create_session(user["username"], user["id"], user["first_name"])

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=3600,
    )
    return {"message": "Logged in successfully"}

@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return full user profile from database"""
    user = {key: current_user[key] for key in current_user.keys()}
    return user

@router.post("/logout")
def logout(response: Response, session_id: Optional[str] = Cookie(default=None)):
    if session_id and session_id in sessions:
        del sessions[session_id]
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "Logged out"}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    first_name: str

@router.post("/register")
def register_user(user: CreateUserRequest):
    existing = db.read_user(username=user.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    db.create_user(user.username, user.password, user.first_name, favorites=[])
    return {"message": f"User '{user.username}' created successfully"}
