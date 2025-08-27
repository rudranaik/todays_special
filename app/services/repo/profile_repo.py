from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.core.models import UserProfile
from app.services.exceptions import RepoError

class JSONUserProfileRepo:
    """Repo for user profile data, stored in a single JSON file."""

    def __init__(self, settings):
        self._fpath = Path(settings.data_dir) / "profile.json"

    def load(self) -> Optional[UserProfile]:
        """Load profile from disk. Returns None if not found."""
        if not self._fpath.exists():
            return None
        try:
            with self._fpath.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return UserProfile(**data)
        except (IOError, json.JSONDecodeError, TypeError) as e:
            raise RepoError(f"Could not load profile from {self._fpath}: {e}") from e

    def save(self, profile: UserProfile) -> None:
        """Save profile to disk."""
        try:
            payload = profile.model_dump_json(indent=2)
            self._fpath.write_text(payload, encoding="utf-8")
        except (IOError, TypeError) as e:
            raise RepoError(f"Could not save profile to {self._fpath}: {e}") from e
