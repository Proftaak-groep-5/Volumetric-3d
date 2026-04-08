from ..crud.museum import get_all_museums as crud_get_all_museums
from ..services import recording as recording_service


async def get_all_museums(db):
    museums = await crud_get_all_museums(db)
    for museum in museums:
        museum.recordings = recording_service.get_recordings_by_museum(museum.museumid)

    return museums