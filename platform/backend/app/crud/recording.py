from sqlalchemy import select

from ..models.recording import Recording


async def get_recordings_by_museum(db, museum_id):
    return await db.execute(
        select(Recording).where(Recording.museumid == museum_id)
    ).scalars().all()