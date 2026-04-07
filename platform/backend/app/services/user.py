import uuid

from ..crud import user as user_crud
import hashlib
import secrets
import base64
from typing import Optional
import bcrypt


def get_user_by_id(db, user_id: int):
    return user_crud.get_by_id(db, id=user_id)


def register_user(db, email: str, username: str, password: str, repeated_password: str, first_name: str, last_name: str):
    if password != repeated_password:
        raise ValueError("Passwords do not match")

    existing_user = user_crud.get_by_email(db, email=email)
    if existing_user:
        raise ValueError("Email already registered")

    uuid = user_crud.createUser(db, email=email, username=username, first_name=first_name, last_name=last_name)

    hashed_password = bcrypt.hashpw(password, uuid) # Hash password

    user_crud.updatePassword(db, uuid=uuid, password=hashed_password)

