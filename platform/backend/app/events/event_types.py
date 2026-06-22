from pydantic import BaseModel

class museum_created(BaseModel):
    museumid: str
    name: str
    owner: str
    description: str