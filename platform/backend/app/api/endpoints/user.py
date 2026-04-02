from django.db import router
from fastapi import APIRouter, HTTPException
from ...core.deps import DbSession
from ...schemas.user import UserRead, UserCreate
from ...crud import user as user_crud

router = APIRouter("prefix=/users", tags=["users"])

@router.post("/register", response_model=UserRead, status_code=201)
async def register_user(
    user_in: UserCreate,
    db: DbSession
):
    existing_user = await user_crud.get_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = await user_crud.create(db, obj_in=user_in)

    return user


