from pydantic import BaseModel, Field


#Base
class MuseumBase(BaseModel):
    name: str = Field(..., max_length=255)

#Create
class MuseumCreate(MuseumBase):
    pass

#Read
class MuseumRead(MuseumBase):
    museumid: int

    class Config:
        orm_mode = True

#Update
class MuseumUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)