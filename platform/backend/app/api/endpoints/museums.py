from typing import List

from fastapi import APIRouter, HTTPException

from ...core.deps import DbSession
from ...schemas.museum import MuseumRead, MuseumCreate
from ...services import museum as museum_service

router = APIRouter(prefix="/museums", tags=["museums"])

@router.get("/getAll", response_model=List[MuseumRead], status_code=201, responses={400: {"description": "Invalid request"}})
async def get_all_museums(
        db: DbSession
):
    try:
        museums = await museum_service.get_all_museums(db)
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