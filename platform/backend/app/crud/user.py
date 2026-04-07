from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email)
    )

async def get_by_id(db: AsyncSession, id: int) -> User | None:
    result = await db.execute(
        select(User).where(User.userid == id)
    )
    return result.scalars().first()

async def createUser(db: AsyncSession, email: str, username: str, first_name: str, last_name: str) -> bytes:
    new_user = User(
        email=email,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    await db.execute(
        select(User).where(User.email == email)
    )
    return new_user

async def updatePassword(db: AsyncSession, uuid: bytes, password: bytes):
    result = await db.execute(
        select(User).where(User.userid == uuid)
    )
    user = result.scalars().first()
    if user:
        user.hashed_password = password
        user.updated_at = datetime.utcnow()
        await db.commit()