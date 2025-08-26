from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings
from app.services.metrics import MetricsLogger

router = APIRouter(tags=["metrics"])


def get_settings() -> Settings:
    return Settings()


class UILatency(BaseModel):
    name: str = Field(..., description="Metric name, e.g., 'suggest_render' or 'transcribe_e2e'")
    duration_ms: float = Field(..., ge=0)
    extra: dict | None = None


@router.post("/api/v1/metrics/ui")
def log_ui_latency(payload: UILatency, settings: Settings = Depends(get_settings)):
    logger = MetricsLogger(settings)
    logger.log_latency(payload.name, payload.duration_ms, origin="frontend", extra=payload.extra)
    return {"ok": True}

