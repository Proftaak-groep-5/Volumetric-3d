from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://testuser:VolCap3D1234!@localhost:5432/testdb")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

#Base for all models
class Base(DeclarativeBase):
    pass

#import models to register them with SQLAlchemy
from ..models import user

# create tables using the async engine's run_sync (do not run on import in production)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# optionally expose a helper to initialize DB (call from FastAPI startup)
def schedule_init_db():
    asyncio.create_task(init_db())

#FastAPI dependency
async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()