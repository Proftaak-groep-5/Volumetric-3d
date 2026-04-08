from ..crud.recording import get_recordings_by_museum as crud_get_recordings_by_museum


async def get_recordings_by_museum(db, museum_id):
    return await crud_get_recordings_by_museum(db, museum_id)