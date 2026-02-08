from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from utils import db

router: APIRouter = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreateRequest(BaseModel):
    comment: str = Field(min_length=1)


class FeedbackUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1)
    first_name: str | None = Field(default=None, min_length=1)
    comment: str | None = Field(default=None, min_length=1)


class FeedbackItem(BaseModel):
    id: int
    username: str
    first_name: str
    comment: str
    comment_date: str | None = None


@router.post(path="/", response_model=FeedbackItem, status_code=201)
def create_feedback(
    payload: FeedbackCreateRequest, current_user=Depends(get_current_user)
) -> FeedbackItem:
    feedback_id = db.create_feedback(
        username=current_user["username"],
        first_name=current_user["first_name"], comment=payload.comment
    )
    created = db.get_feedback(feedback_id=feedback_id)
    if created is None:
        raise HTTPException(status_code=500, detail="Failed to create feedback")
    return FeedbackItem(**created)


@router.get(path="/", response_model=list[FeedbackItem])
def get_feedback_items() -> list[FeedbackItem]:
    return [FeedbackItem(**item) for item in db.list_feedback()]


@router.get(path="/{feedback_id}", response_model=FeedbackItem)
def get_feedback_item(feedback_id: int) -> FeedbackItem:
    feedback = db.get_feedback(feedback_id=feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return FeedbackItem(**feedback)


@router.patch(path="/{feedback_id}", response_model=FeedbackItem)
def update_feedback_item(
    feedback_id: int, payload: FeedbackUpdateRequest
) -> FeedbackItem:
    if (
        payload.username is None
        and payload.first_name is None
        and payload.comment is None
    ):
        raise HTTPException(status_code=400, detail="No fields provided to update")

    updated = db.update_feedback(
        feedback_id=feedback_id,
        username=payload.username,
        first_name=payload.first_name,
        comment=payload.comment,
    )
    if updated is False:
        raise HTTPException(status_code=404, detail="Feedback not found")

    feedback = db.get_feedback(feedback_id=feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return FeedbackItem(**feedback)


@router.delete(path="/{feedback_id}")
def delete_feedback_item(feedback_id: int) -> dict:
    deleted = db.delete_feedback(feedback_id=feedback_id)
    if deleted is False:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"message": "Feedback deleted"}
