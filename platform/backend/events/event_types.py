from pydantic import BaseModel

class MuseumCreatedEvent(BaseModel):
    museumid: str
    name: str
    owner: str
    description: str