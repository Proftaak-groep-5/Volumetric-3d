import uuid
from typing import List

from fastapi import APIRouter, HTTPException

from ...contracts.museum_contract import CreateMuseumContract
from platform.backend.events.publisher import publish_museum_event
from app.core.deps import DbSession
from app.schemas.museum import MuseumRead
from app.services import museum as museum_service
from app.services import recording as recording_service



router = APIRouter(prefix="/museums", tags=["museums"])

@router.get("/getAll", response_model=List[MuseumRead], status_code=201, responses={400: {"description": "Invalid request"}})
async def get_all_museums(
        db: DbSession
):
    try:
        museums = await museum_service.get_all_museums(db)
        for museum in museums:
            print(f"Fetching recordings for museum: {museum.name} (ID: {museum.museumid})")
            museum.recordings = await recording_service.get_recordings_by_museum(db, museum.museumid)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return museums

#OLD ENDPOINT => NO EVENTS
# @router.post("/createMuseum", response_model=MuseumRead, status_code=201, responses={400: {"description": "Invalid request"}})
# async def create_museum(
#         db: DbSession,
#         payload: MuseumCreate
# ):
#     try:
#         museum = await museum_service.create_museum(db, name=payload.name, description=payload.description)
#     except ValueError as exc:
#         raise HTTPException(status_code=400, detail=str(exc)) from exc
#
#     return museum

# NEW ENDPOINT => RABBITMQ EVENT
@router.post("/createMuseum")
async def create_museum(museum: dict):
    validated = CreateMuseumContract(**museum)

    publish_museum_event(validated.model_dump())

    return {"status": "event_sent"}




# NEW ENDPOINT => CUSTOM EVENT (FUN FOR AFTER HOURS - Herman J)
# @router.post("/createMuseum")
# def create_museum(data: dict):
#     event = BaseEvent(
#         event_type="museum_created",
#         payload=data
#     )
#
#     event_bus.publish(event)
#
#     return {"status": "event_sent"}


@router.get("/getById", response_model=MuseumRead, status_code=200, responses={400: {"description": "Invalid request"}})
async def get_museum_by_id(
        db: DbSession,
        museumid: uuid.UUID
):
    try:
        museum = await museum_service.get_museum_by_id(db, museumid)
        if not museum:
            raise ValueError("Museum not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return museum