from sqlalchemy.ext.asyncio import AsyncSession

from ..crud import museum as museum_crud
from ..services import recording as recording_service


async def get_all_museums(db):
    museums = await museum_crud.get_all_museums(db)
    for museum in museums:
        museum.recordings = recording_service.get_recordings_by_museum(museum.museumid)

    return museums

async def create_museum(
        db: AsyncSession,
        name: str,
        description: str
):
    return await museum_crud.create_museum(db, name=name, description=description)