from ..models.museum import Museum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def get_museum_by_id(db: AsyncSession, museum_id):
    result = await db.execute(
        select(Museum).where(Museum.museumid == museum_id)
    )
    return result.scalars().first()

async def get_all_museums(db: AsyncSession):
    result = await db.execute(
        select(Museum)
    )
    return result.scalars().all()

async def search_museums(db: AsyncSession, query: str):
    result = await db.execute(
        select(Museum).where(Museum.name.ilike(f"%{query}%"))
    )
    return result.scalars().all()

async def create_museum(db: AsyncSession, name: str, description: str, image_url: str | None = None):
    new_museum = Museum(
        name=name,
        owner= None,  # Set owner to None, implement logged in user here
        recordings= [],  # Initialize with an empty list of recordings
        description=description,
    )
    db.add(new_museum)
    await db.commit()
    await db.refresh(new_museum)
    return new_museum