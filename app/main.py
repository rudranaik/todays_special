from __future__ import annotations

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.suggest import router as suggest_router
from app.config import Settings

from dotenv import load_dotenv
import os

from app.api.v1.suggest import router as suggest_router
from app.api.v1.pantry import router as pantry_router
load_dotenv()  # populates os.environ from .env


print("OPENAI_API_KEY from env:", os.getenv("OPENAI_API_KEY"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data dir exists so repos can write
    settings = Settings()
    os.makedirs(settings.data_dir, exist_ok=True)
    yield

def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="Pantry Suggest API", version="1.0", lifespan=lifespan)

    # CORS (narrow it down in .env via CORS_ALLOW_ORIGINS if you want)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(pantry_router)  
    app.include_router(suggest_router)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz():
        return {"status": "ready"}

    return app

app = create_app()
