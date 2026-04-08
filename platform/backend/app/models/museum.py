#museum object to hold recordings
import uuid

from .. import db
from sqlalchemy import Column, String, Integer, ForeignKey, UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from ..core.database import Base

class Museum(Base):
    __tablename__ = "museumdto"

    museumid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name = Column(String, unique=True, index=True)
    owner = Column(UUID, index=True, foreign_key="userdata.userid")
    recordings = relationship("Recording", back_populates="museum")
    description = Column(String)