from pydantic import BaseModel

class CreateMuseumContract(BaseModel):
    name: str
    description: str
    image_Url: str

class ReceivedCreateMuseumContract(BaseModel):
    event_type: str
    name: str
    description: str
    image_Url: str