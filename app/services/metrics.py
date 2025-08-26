from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional, Dict

from app.config import Settings
from app.services.repo.json_repo import _locked  # reuse existing cross-platform lock


class MetricsLogger:
    """Append-only JSONL logger for latency metrics under data/.

    Writes one JSON object per line with fields:
      - ts: ISO timestamp (UTC)
      - kind: "latency"
      - name: short name (e.g., "transcribe", "suggest_render")
      - origin: "backend" | "frontend"
      - duration_ms: float
      - extra: optional dict with contextual fields
    """

    def __init__(self, settings: Optional[Settings] = None, filename: str = "latency_log.jsonl") -> None:
        self.settings = settings or Settings()
        os.makedirs(self.settings.data_dir, exist_ok=True)
        self.path = os.path.join(self.settings.data_dir, filename)

    def log_latency(
        self,
        name: str,
        duration_ms: float,
        origin: str,
        extra: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        corr_id: Optional[str] = None,
    ) -> None:
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "kind": "latency",
            "name": name,
            "origin": origin,
            "duration_ms": float(duration_ms),
        }
        if user_id:
            entry["user"] = user_id
        if corr_id:
            entry["corr"] = corr_id
        if extra:
            entry["extra"] = extra
        line = (json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with _locked(self.path) as f:
                f.seek(0, os.SEEK_END)
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            # Metrics should never impact user flows; swallow errors.
            pass
