from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from repositories.feedback import (
    create_feedback as create_feedback_repo,
    delete_feedback,
    get_feedback,
    list_feedback,
    update_feedback,
)
from routers.auth import get_current_user

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
    feedback_id = create_feedback_repo(
        username=current_user["username"],
        first_name=current_user["first_name"],
        comment=payload.comment,
    )
    created = get_feedback(feedback_id=feedback_id)
    if created is None:
        raise HTTPException(status_code=500, detail="Failed to create feedback")
    return FeedbackItem(**created)


@router.get(path="/", response_model=list[FeedbackItem])
def get_feedback_items(current_user=Depends(get_current_user)) -> list[FeedbackItem]:
    return [
        FeedbackItem(**item)
        for item in list_feedback(username=current_user["username"])
    ]


@router.get(path="/{feedback_id}", response_model=FeedbackItem)
def get_feedback_item(feedback_id: int) -> FeedbackItem:
    feedback = get_feedback(feedback_id=feedback_id)
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

    updated = update_feedback(
        feedback_id=feedback_id,
        username=payload.username,
        first_name=payload.first_name,
        comment=payload.comment,
    )
    if updated is False:
        raise HTTPException(status_code=404, detail="Feedback not found")

    feedback = get_feedback(feedback_id=feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return FeedbackItem(**feedback)


@router.delete(path="/{feedback_id}")
def delete_feedback_item(feedback_id: int) -> dict:
    deleted = delete_feedback(feedback_id=feedback_id)
    if deleted is False:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"message": "Feedback deleted"}
