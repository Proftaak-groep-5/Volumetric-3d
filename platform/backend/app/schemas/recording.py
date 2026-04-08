from pydantic import Field, BaseModel


#Base
class RecordingBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    file_url: str = Field(..., max_length=255)

#Create
class RecordingCreate(RecordingBase):
    pass

#Read
class RecordingRead(RecordingBase):
    recordingid: int
    museumid: int

    class Config:
        orm_mode = True

#Update
class RecordingUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    file_url: str | None = Field(None, max_length=255)