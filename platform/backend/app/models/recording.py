from sqlalchemy import Column, Integer, String, UUID, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.testing.schema import mapped_column

from ..core.database import Base


class Recording(Base):
    __tablename__ = "recordingdto"

    recordingid = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    file_url = Column(String)
    museumid = Column(UUID, ForeignKey("museumdto.museumid"))
    owner = Column(UUID, ForeignKey("userdata.userid"), index=True)

    museum = relationship("Museum", back_populates="recordings")