import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from ...events.event_types import MuseumCreatedEvent

from ..crud import museum as museum_crud
from ..crud import recording as recording_crud


async def get_all_museums(db):
    museums = await museum_crud.get_all_museums(db)
    for m in museums:
        m.recordings = await recording_crud.get_recordings_by_museum(db, m.museumid)
        for r in m.recordings:
            r.file_url = r.file_url or ""
    return museums

async def create_museum(
        db: AsyncSession,
        publisher: EventPublisher,
        name: str,
        description: str
):
    museum = await museum_crud.create_museum(db, name=name, description=description)

    event = MuseumCreatedEvent(
        name=name,
        description=description
    )

    await publisher.publish(
        exchange_name="museum.events",
        routing_key="museum.created",
        event=event.model_dump()
    )

    return museum

async def get_museum_by_id(db, museumid):
    museum = await museum_crud.get_museum_by_id(db, museumid)
    print(museumid)
    museum.recordings = await recording_crud.get_recordings_by_museum(db, museumid)
    for r in museum.recordings:
        r.file_url = r.file_url or ""
    return museum

