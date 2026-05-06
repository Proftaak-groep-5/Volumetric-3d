from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalars().first()


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(
        select(User).where(User.username == username)
    )
    return result.scalars().first()


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.userid == user_id)
    )
    return result.scalars().first()


async def create_user(
    db: AsyncSession,
    email: str,
    username: str,
    hashed_password: str,
    first_name: str | None,
    last_name: str | None,
    bio: str | None = None,
    avatar_url: str | None = None,
) -> User:
    new_user = User(
        email=email,
        username=username,
        hashed_password=hashed_password,
        first_name=first_name,
        last_name=last_name,
        bio=bio,
        avatar_url=avatar_url,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


async def update_password(db: AsyncSession, user_id: uuid.UUID, password: str) -> User | None:
    result = await db.execute(
        select(User).where(User.userid == user_id)
    )
    user = result.scalars().first()
    if user:
        user.hashed_password = password
        user.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)

    return user