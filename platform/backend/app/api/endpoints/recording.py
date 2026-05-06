from fastapi import APIRouter, HTTPException

from ...schemas.recording import RecordingCreate
from ...services import recording as recording_service
from ...core.deps import DbSession

router = APIRouter(prefix="/recordings", tags=["recordings"])

@router.post("/createRecording", status_code=201)
async def create_recording(
        db: DbSession,
        payload: RecordingCreate
):
    try:
        recording = await recording_service.create_recording(
            db,
            museumid=payload.museumid,
            name=payload.name,
            description=payload.description
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return recording