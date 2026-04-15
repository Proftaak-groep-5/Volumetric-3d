from pydantic import BaseModel, Field, AliasChoices


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
    museumid: int

    class Config:
        orm_mode = True

#Update
class MuseumUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)