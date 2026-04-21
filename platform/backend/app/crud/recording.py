from sqlalchemy import select

from ..models.recording import Recording


async def get_recordings_by_museum(db, museumid):
    result = await db.execute(
        select(Recording).where(Recording.museumid == museumid)
    )
    return result.scalars().all()

async def create_recording(db, museumid, name, description):
    new_recording = Recording(
        museumid=museumid,
        name=name,
        description=description,
    )
    db.add(new_recording)
    await db.commit()
    await db.refresh(new_recording)
    return new_recording