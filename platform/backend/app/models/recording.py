import uuid

from sqlalchemy import Column, Integer, String, UUID, ForeignKey
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.testing.schema import mapped_column

from ..core.database import Base


class Recording(Base):
    __tablename__ = "recordingdto"


    recordingid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name = Column(String, index=True, nullable=True)
    description = Column(String, nullable=True)
    file_url = Column(String, nullable=True)
    museumid = Column(UUID, ForeignKey("museumdto.museumid"))
    owner = Column(UUID, ForeignKey("userdata.userid"), index=True)

    museum = relationship("Museum", back_populates="recordings", lazy="selectin")
