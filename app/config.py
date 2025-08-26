from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
from dotenv import load_dotenv
import os
load_dotenv()  # populates os.environ from .env
# print("OPENAI_API_KEY from env:", os.getenv("OPENAI_API_KEY"))

class Settings(BaseSettings):
    # LLM
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model_extract: str = Field("gpt-5-nano", env="OPENAI_MODEL_EXTRACT")
    openai_model_suggest: str = Field("gpt-5-nano", env="OPENAI_MODEL_SUGGEST")

    # ASR
    asr_model: str = Field("tiny", env="ASR_MODEL")
    asr_compute_type: str = Field("int8", env="ASR_COMPUTE_TYPE")
    asr_beam_size: int = Field(1, env="ASR_BEAM_SIZE")

    # Toggle for using OpenAI vs local parser
    itemsnap_use_openai: bool = Field(True, env="ITEMSNAP_USE_OPENAI")

    # Storage
    data_dir: str = Field("data", env="DATA_DIR")
    pantry_file: str = Field("data/pantry.json", env="PANTRY_FILE")
    events_file: str = Field("data/inventory_log.jsonl", env="EVENTS_FILE")

    # CORS (to wire later in main app)
    cors_allow_origins: List[str] = Field(default_factory=lambda: ["http://127.0.0.1:8001"])

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
