from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .core.database import init_db
from .api.endpoints.user import router as user_router
from .api.endpoints.museums import router as museum_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(user_router)
app.include_router(museum_router)

# List of allowed origins
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://your-production-frontend.com",
    # "*"   # ← only for dev, not recommended in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # or ["*"] for dev
    allow_credentials=True,         # set to True if you use cookies/auth
    access_control_allow_methods=["*"],  # or specify allowed methods
    access_control_allow_headers=["*"],  # or specify allowed headers
)

@app.get("/")
async def root():
    return {"message": "Something is working!"}