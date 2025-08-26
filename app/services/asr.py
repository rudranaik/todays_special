from __future__ import annotations

from typing import Optional
from .exceptions import ASRError
from app.config import Settings

class WhisperASR:
    """
    Thin wrapper around faster-whisper. No fallback: errors bubble as ASRError.
    """
    def __init__(self, settings: Settings):
        try:
            from faster_whisper import WhisperModel  # local import to avoid hard dep at import-time
        except Exception as e:  # pragma: no cover
            raise ASRError("faster-whisper not installed. `pip install faster-whisper`") from e

        try:
            self._model = WhisperModel(
                settings.asr_model,
                compute_type=settings.asr_compute_type,
            )
            self._beam_size = settings.asr_beam_size
            # Expose config for metrics
            self.model_name = settings.asr_model
            self.compute_type = settings.asr_compute_type
            self.beam_size = settings.asr_beam_size
        except Exception as e:
            raise ASRError(f"Failed to initialize Whisper model: {e}") from e

    def transcribe_file(self, audio_path: str, language: Optional[str] = None) -> str:
        try:
            segments, _info = self._model.transcribe(
                audio_path,
                beam_size=self._beam_size,
                language=language,
            )
            return " ".join(seg.text.strip() for seg in segments)
        except Exception as e:
            raise ASRError(f"ASR transcription failed: {e}") from e
