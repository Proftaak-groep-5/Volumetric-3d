from pydantic import Field, BaseModel


#Base
class RecordingBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    file_url: str = Field(..., max_length=255)

#Create
class RecordingCreate(RecordingBase):
    museumid: str

#Read
class RecordingRead(RecordingBase):
    recordingid: str
    museumid: str

    class Config:
        orm_mode = True

#Update
class RecordingUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    file_url: str | None = Field(None, max_length=255)