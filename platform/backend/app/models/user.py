from datetime import datetime
import uuid 
from sqlalchemy import String, Boolean, DateTime, Column, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, Mapped, mapped_column


Base = declarative_base()

class User(Base):
    __tablename__ = "userdata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        default=uuid.uuid4,
        index=True
    )