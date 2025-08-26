from __future__ import annotations

import os
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
import time
from pydantic import BaseModel

from app.config import Settings
from app.core.models import InventoryEvent, Item
from app.services.asr import WhisperASR
from app.services.exceptions import ASRError, LLMError, RepoError
from app.services.llm import OpenAIItemExtractor
from app.services.repo.json_repo import JSONEventRepo
from app.services.metrics import MetricsLogger

router = APIRouter(tags=["ingest"])

# ---- DI helpers --------------------------------------------------------------

def get_settings() -> Settings:
    return Settings()

def get_asr(settings: Settings = Depends(get_settings)) -> WhisperASR:
    return WhisperASR(settings)

def get_extractor(settings: Settings = Depends(get_settings)) -> OpenAIItemExtractor:
    return OpenAIItemExtractor(settings)

def get_event_repo(settings: Settings = Depends(get_settings)) -> JSONEventRepo:
    return JSONEventRepo(settings)

# ---- Models ------------------------------------------------------------------

class TextIngestRequest(BaseModel):
    text: str

# ---- Routes ------------------------------------------------------------------

@router.post("/api/v1/ingest/transcribe")
async def transcribe(
    file: UploadFile = File(..., description="Audio file (webm/mp3/wav/m4a)"),
    language: Optional[str] = Form(None, description="ISO code like 'en','hi'"),
    asr: WhisperASR = Depends(get_asr),
):
    # persist upload to a temp file for faster-whisper
    logger = MetricsLogger()
    try:
        suffix = os.path.splitext(file.filename or "")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read upload: {e}")

    try:
        t0 = time.perf_counter()
        transcript = asr.transcribe_file(tmp_path, language=language)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        # best-effort log
        logger.log_latency(
            name="transcribe",
            duration_ms=dt_ms,
            origin="backend",
            extra={"bytes": len(content or b""), "language": language or None},
        )
    except ASRError as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return {"transcript": transcript}

@router.post("/api/v1/ingest/text")
async def extract_from_text(
    request: TextIngestRequest,
    extractor: OpenAIItemExtractor = Depends(get_extractor),
    events: JSONEventRepo = Depends(get_event_repo),
):
    try:
        items: List[Item] = extractor.extract(request.text)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"Item extraction failed: {e}")

    try:
        events.append(InventoryEvent(type="ingest", payload={"count": len(items), "source": "text"}))
    except RepoError:
        pass

    return {
        "items": [i.dict(exclude={"norm_name", "norm_unit"}) for i in items],
    }

@router.post("/api/voice/transcribe_extract")
async def transcribe_and_extract(
    file: UploadFile = File(..., description="Audio file (webm/mp3/wav/m4a)"),
    language: Optional[str] = Form(None, description="ISO code like 'en','hi'"),
    asr: WhisperASR = Depends(get_asr),
    extractor: OpenAIItemExtractor = Depends(get_extractor),
    events: JSONEventRepo = Depends(get_event_repo),
):
    # persist upload to a temp file for faster-whisper
    try:
        suffix = os.path.splitext(file.filename or "")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read upload: {e}")

    try:
        transcript = asr.transcribe_file(tmp_path, language=language)
    except ASRError as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    try:
        items: List[Item] = extractor.extract(transcript)
    except LLMError as e:
        # return transcript so user can still copy/edit, but signal failure clearly
        raise HTTPException(status_code=502, detail=f"Item extraction failed: {e}")

    # log event (best-effort)
    try:
        events.append(InventoryEvent(type="ingest", payload={"count": len(items), "bytes": len(content)}))
    except RepoError:
        pass

    return {
        "transcript": transcript,
        "items": [i.dict(exclude={"norm_name", "norm_unit"}) for i in items],
    }
