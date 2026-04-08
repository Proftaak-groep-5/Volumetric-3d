import uuid

from fastapi import APIRouter, HTTPException
from pydantic import EmailStr

from ...core.deps import DbSession
from ...schemas.user import UserRead, UserRegister
from ...services import user as user_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post(
    "/register",
    response_model=UserRead,
    status_code=201,
    responses={400: {"description": "Invalid registration request"}},
)
async def register_user(
    payload: UserRegister,
    db: DbSession,
):
    try:
        user = await user_service.register_user(
            db,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            repeated_password=payload.repeated_password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            bio=payload.bio,
            avatar_url=payload.avatar_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return user


@router.get(
    "/by-email",
    response_model=UserRead,
    responses={404: {"description": "User not found"}},
)
async def get_user_by_email(email: EmailStr, db: DbSession):
    user = await user_service.get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

@router.get(
    "/{user_id}",
    response_model=UserRead,
    responses={404: {"description": "User not found"}},
)
async def get_user(
    user_id: uuid.UUID,
    db: DbSession,
):
    user = await user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


