from fastapi import FastAPI
from ..app.core.database import get_db
app = FastAPI()

@app.on_event("startup")
def on_startup():
    get_db()

@app.get("/")
async def root():
    return {"message": "Something is working!"}

@app.post("/test")
async def test():
    return {"message": "This is a test endpoint!"}
