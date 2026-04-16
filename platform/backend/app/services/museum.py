import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..crud import museum as museum_crud
from ..crud import recording as recording_crud


async def get_all_museums(db):
    museums = await museum_crud.get_all_museums(db)
    return museums

async def create_museum(
        db: AsyncSession,
        name: str,
        description: str
):
    return await museum_crud.create_museum(db, name=name, description=description)

async def get_museum_by_id(db, museumid):
    museum = await museum_crud.get_museum_by_id(db, museumid)
    print(museumid)
    museum.recordings = await recording_crud.get_recordings_by_museum(db, museumid)
    return museum

