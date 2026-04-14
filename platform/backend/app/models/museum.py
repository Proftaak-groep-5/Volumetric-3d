#museum object to hold recordings
import uuid

from .. import db
from sqlalchemy import Column, String, Integer, ForeignKey, UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column, foreign
from ..core.database import Base

class Museum(Base):
    __tablename__ = "museumdto"

    museumid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name = Column(String, unique=True, index=True)
    owner = mapped_column(UUID, ForeignKey("userdata.userid"), index=True)
    recordings = relationship("Recording", back_populates="museum")
    description = Column(String)