from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
from app.core.models import Item, Pantry, InventoryEvent
from .exceptions import RepoError

class PantryRepo(ABC):
    @abstractmethod
    def load(self) -> Pantry: ...
    @abstractmethod
    def save(self, pantry: Pantry) -> None: ...

class EventRepo(ABC):
    @abstractmethod
    def append(self, event: InventoryEvent) -> None: ...
