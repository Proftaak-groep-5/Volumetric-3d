from contextlib import asynccontextmanager
from fastapi import FastAPI
from ..app.core.database import init_db
from ..app.api.endpoints.user import router as user_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(user_router)
users = []
@app.get("/")
async def root():
    return {"message": "Something is working!"}