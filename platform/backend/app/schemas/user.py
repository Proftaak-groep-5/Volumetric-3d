from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
import uuid

# Base
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., max_length=255)
    first_name: str | None = Field(None, max_length=255)
    last_name: str | None = Field(None, max_length=255)
    bio: str | None = None
    avatar_url: str | None = Field(None, max_length=255)

# Create / Register
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserRegister(UserCreate):
    repeated_password: str = Field(..., min_length=8)

# Read
class UserRead(UserBase):
    userid: uuid.UUID
    is_active: bool
    is_verified: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

# Update
class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(None, max_length=255)
    first_name: str | None = Field(None, max_length=255)
    last_name: str | None = Field(None, max_length=255)
    bio: str | None = None
    avatar_url: str | None = Field(None, max_length=255)
    password: str | None = Field(None, min_length=8)

# Login
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Token Response
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    uuid: str | None = None

