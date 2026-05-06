import uuid
from typing import List

from pydantic import BaseModel, Field, AliasChoices

from ..schemas.recording import RecordingRead


#Base
class MuseumBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: str = Field(...)
    image_Url:str | None = Field(
        None,
        max_length=255,
        validation_alia=AliasChoices("image_Url", "imageUrl"),
    )

#Create
class MuseumCreate(MuseumBase):
    pass

#Read
class MuseumRead(MuseumBase):
    museumid: uuid.UUID
    recordings: List[RecordingRead] = []

    class Config:
        orm_mode = True

#Update
class MuseumUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)