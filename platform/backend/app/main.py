from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.endpoints.user import router as user_router
from .api.endpoints.museums import router as museum_router
from .api.endpoints.recording import router as recording_router
from .core.database import schedule_init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await schedule_init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(user_router)
app.include_router(museum_router)
app.include_router(recording_router)


allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS")
if allowed_origins_env:
    origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
else:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Something is working!"}