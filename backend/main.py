import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from api.routes import router
from api.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    print("Initializing database...")
    await init_db()
    print("Database initialized.")
    yield
    print("Shutting down...")


app = FastAPI(
    title="2careai Voice AI Agent",
    version="1.0.0",
    lifespan=lifespan,
)

_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(router, prefix="/api")
app.include_router(ws_router, prefix="/ws")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
