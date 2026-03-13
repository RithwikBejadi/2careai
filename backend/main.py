from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    print("Initializing database...")
    await init_db()
    print("Database initialized.")
    yield
    print("Shutting down...")

app = FastAPI(
    title = "Voice AI Agent - Clinical Appointments",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

