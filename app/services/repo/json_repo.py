from __future__ import annotations

import io
import json
import os
import tempfile
from contextlib import contextmanager
from typing import Iterator

from app.core.models import Pantry, Item, InventoryEvent
from app.services.exceptions import RepoError
from app.config import Settings
from datetime import datetime

# Cross-platform file lock (fcntl for *nix; msvcrt for Windows)
@contextmanager
def _locked(path: str) -> Iterator[io.FileIO]:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    f = open(path, "a+b")  # create if missing
    try:
        try:
            import fcntl  # type: ignore
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            locker = ("fcntl", None)
        except Exception:
            try:
                import msvcrt  # type: ignore
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                locker = ("msvcrt", 1)
            except Exception as e:
                f.close()
                raise RepoError(f"Could not lock file {path}: {e}") from e
        yield f
    finally:
        # Unlock
        try:
            if locker[0] == "fcntl":
                import fcntl  # type: ignore
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                import msvcrt  # type: ignore
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, locker[1])
        except Exception:
            pass
        f.close()


def _atomic_write(path: str, data: bytes) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "wb") as w:
            w.write(data)
            w.flush()
            os.fsync(w.fileno())
        os.replace(tmp, path)
    except Exception as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise RepoError(f"Atomic write failed for {path}: {e}") from e


class JSONPantryRepo:
    def __init__(self, settings: Settings):
        self.path = settings.pantry_file

    def load(self) -> Pantry:
        try:
            if not os.path.exists(self.path):
                return Pantry(items=[])
            with _locked(self.path) as f:
                f.seek(0)
                raw = f.read() or b"{}"
            obj = json.loads(raw.decode("utf-8"))
            items = [Item(**it) for it in obj.get("items", [])]
            return Pantry(items=items)
        except Exception as e:
            raise RepoError(f"Failed to load pantry from {self.path}: {e}") from e

    def save(self, pantry: Pantry) -> None:
        try:
            payload = json.dumps({"items": [i.dict(exclude={"norm_name", "norm_unit"}) for i in pantry.items]},
                                 ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            # Lock only to read/validate existing, then atomic replace
            _atomic_write(self.path, payload)
        except Exception as e:
            raise RepoError(f"Failed to save pantry to {self.path}: {e}") from e


class JSONEventRepo:
    def __init__(self, settings: Settings):
        self.path = settings.events_file

    def append(self, event: InventoryEvent) -> None:
        try:
            line = (json.dumps(event.dict(), ensure_ascii=False, separators=(",", ":"),default=str) + "\n").encode("utf-8")
            with _locked(self.path) as f:
                f.seek(0, os.SEEK_END)
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            raise RepoError(f"Failed to append event to {self.path}: {e}") from e
