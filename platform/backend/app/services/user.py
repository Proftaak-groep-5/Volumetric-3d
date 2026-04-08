from ..crud import user as user_crud
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def get_user_by_id(db: AsyncSession, user_id):
    return await user_crud.get_by_id(db, user_id=user_id)


async def get_user_by_email(db: AsyncSession, email: str):
    return await user_crud.get_by_email(db, email=email)


async def register_user(
    db: AsyncSession,
    email: str,
    username: str,
    password: str,
    repeated_password: str,
    first_name: str | None,
    last_name: str | None,
    bio: str | None = None,
    avatar_url: str | None = None,
):
    if password != repeated_password:
        raise ValueError("Passwords do not match")

    existing_user = await user_crud.get_by_email(db, email=email)
    if existing_user:
        raise ValueError("Email already registered")

    existing_username = await user_crud.get_by_username(db, username=username)
    if existing_username:
        raise ValueError("Username already taken")

    hashed_password = _hash_password(password)

    return await user_crud.create_user(
        db,
        email=email,
        username=username,
        hashed_password=hashed_password,
        first_name=first_name,
        last_name=last_name,
        bio=bio,
        avatar_url=avatar_url,
    )

