from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from repositories.placement_metrics import (
    create_placement_metric,
    delete_placement_metric,
    get_placement_metric,
    list_placement_metrics,
    update_placement_metric,
)

router: APIRouter = APIRouter(prefix="/placement_metrics", tags=["placement_metrics"])


class PlacementMetricCreateRequest(BaseModel):
    app_id: int
    city: str | None = None
    state: str | None = None
    placementDate: str = Field(min_length=1)


class PlacementMetricUpdateRequest(BaseModel):
    city: str | None = None
    state: str | None = None
    placementDate: str | None = Field(default=None, min_length=1)


class PlacementMetricItem(BaseModel):
    app_id: int
    city: str | None = None
    state: str | None = None
    placementDate: str


@router.post(path="/", response_model=PlacementMetricItem, status_code=201)
def create_placement_metric_item(
    payload: PlacementMetricCreateRequest,
) -> PlacementMetricItem:
    created = create_placement_metric(
        app_id=payload.app_id,
        city=payload.city,
        state=payload.state,
        placement_date=payload.placementDate,
    )
    if created is False:
        raise HTTPException(
            status_code=409, detail="Placement metric already exists for this app_id"
        )

    item = get_placement_metric(app_id=payload.app_id)
    if item is None:
        raise HTTPException(status_code=500, detail="Failed to create placement metric")
    return PlacementMetricItem(**item)


@router.get(path="/", response_model=list[PlacementMetricItem])
def get_placement_metric_items() -> list[PlacementMetricItem]:
    return [PlacementMetricItem(**item) for item in list_placement_metrics()]


@router.patch(path="/{app_id}", response_model=PlacementMetricItem)
def update_placement_metric_item(
    app_id: int, payload: PlacementMetricUpdateRequest
) -> PlacementMetricItem:
    if (
        payload.city is None
        and payload.state is None
        and payload.placementDate is None
    ):
        raise HTTPException(status_code=400, detail="No fields provided to update")

    updated = update_placement_metric(
        app_id=app_id,
        city=payload.city,
        state=payload.state,
        placement_date=payload.placementDate,
    )
    if updated is False:
        raise HTTPException(status_code=404, detail="Placement metric not found")

    item = get_placement_metric(app_id=app_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Placement metric not found")
    return PlacementMetricItem(**item)


@router.delete(path="/{app_id}")
def delete_placement_metric_item(app_id: int) -> dict:
    deleted = delete_placement_metric(app_id=app_id)
    if deleted is False:
        raise HTTPException(status_code=404, detail="Placement metric not found")
    return {"message": "Placement metric deleted"}
