from __future__ import annotations

class ServiceError(RuntimeError):
    """Base class for service-layer errors."""

class LLMError(ServiceError):
    """Errors from the LLM adapter."""

class ASRError(ServiceError):
    """Errors from the ASR adapter."""

class RepoError(ServiceError):
    """Errors from repositories (I/O, parse, schema)."""
