from fastapi import APIRouter, HTTPException
from ...core.deps import DbSession
from ...schemas.user import UserRead, UserCreate
from ...services import user as user_service

router = APIRouter(prefix="/users" , tags=["users"])

@router.post("/register", response_model=UserRead, status_code=201)
async def register_user(
        email: str,
        username: str,
        password: str,
        repeated_password: str,
        firstname: str,
        lastname: str,
        db: DbSession
):
    user = user_service.register_user(
        db,
        email=email,
        username=username,
        password=password,
        repeated_password=repeated_password,
        first_name=firstname,
        last_name=lastname
    )
    return {"message": "Register User!"}

@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    userid: int,
    db: DbSession
):
    user = user_service.get_user_by_id(db, userid)

    return {"message": "Get User!"}

@router.get("/getByEmail", response_model=UserRead)
async def get_user_by_email(
    # email: str,
    # db: DbSession
):
    # user = await user_crud.get_by_email(db, email=email)
    # if not user:
    #     raise HTTPException(status_code=404, detail="User not found")
    # return user
    return {"message": "Get User by Email!"}


