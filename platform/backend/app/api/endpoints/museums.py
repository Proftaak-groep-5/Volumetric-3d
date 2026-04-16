import uuid
from typing import List

from fastapi import APIRouter, HTTPException

from ...core.deps import DbSession
from ...schemas.museum import MuseumRead, MuseumCreate
from ...services import museum as museum_service
from ...services import recording as recording_service



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

@router.post("/createMuseum", response_model=MuseumRead, status_code=201, responses={400: {"description": "Invalid request"}})
async def create_museum(
        db: DbSession,
        payload: MuseumCreate
):
    try:
        museum = await museum_service.create_museum(db, name=payload.name, description=payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return museum

@router.get("/getById", response_model=MuseumRead, status_code=201, responses={400: {"description": "Invalid request"}})
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