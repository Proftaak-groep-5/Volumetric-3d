import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

from .consumer import consume_museum_events

async def main():
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        await consume_museum_events(db)

if __name__ == "__main__":
    asyncio.run(main())