from ..crud import recording as recording_crud


async def get_recordings_by_museum(db, museumid):
    return await recording_crud.get_recordings_by_museum(db, museumid)

async def create_recording(db, museumid, name, description):
    from ..crud.recording import create_recording as crud_create_recording
    return await crud_create_recording(db, museumid, name, description)