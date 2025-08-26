# app/core/models.py
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, Field, validator


# ---------- Core value objects ----------

class Item(BaseModel):
    """A single pantry or parsed item."""
    name: str = Field(..., min_length=1, description="Display name of the item")
    quantity: float = Field(0, ge=0, description="Non-negative quantity")
    unit: Optional[str] = Field(None, description="Normalized unit, e.g., 'g', 'kg', 'ml', 'cup'")
    category: Optional[str] = Field(None, description="High-level category, e.g., 'Grains & Cereals'")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="0.0–1.0 confidence of extraction")
    notes: Optional[str] = None

    # Computed / normalized fields (not persisted directly)
    norm_name: Optional[str] = Field(default=None, exclude=True)
    norm_unit: Optional[str] = Field(default=None, exclude=True)

    @validator("name")
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Item.name cannot be blank")
        return v

    @validator("unit")
    def _normalize_unit_shape(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None

    def key(self) -> tuple[str, Optional[str]]:
        """
        Merge key: (normalized_name, normalized_unit).
        Unit is part of the key to avoid summing apples with apple juice (g vs ml).
        """
        return (self.normalized_name(), self.normalized_unit())

    def normalized_name(self) -> str:
        if self.norm_name is not None:
            return self.norm_name
        # Simple normalization; keep it deterministic and ASCII‑safe.
        n = self.name.lower().strip()
        # Optional: singularization, stop-word removal, etc.
        self.norm_name = n
        return n

    def normalized_unit(self) -> Optional[str]:
        if self.norm_unit is not None:
            return self.norm_unit
        if self.unit is None:
            self.norm_unit = None
            return None
        u = self.unit.lower().strip()
        # Basic canonical map; expand later in services/measurement.py if needed.
        CANON = {
            "grams": "g", "gram": "g", "g": "g",
            "kilogram": "kg", "kilograms": "kg", "kg": "kg",
            "ml": "ml", "millilitre": "ml", "milliliter": "ml", "milliliters": "ml",
            "l": "l", "litre": "l", "liter": "l", "liters": "l",
            "cup": "cup", "cups": "cup",
            "pcs": "piece", "piece": "piece", "pieces": "piece",
            "unit": "piece", "units": "piece",
        }
        self.norm_unit = CANON.get(u, u)  # fall back to input if unknown
        return self.norm_unit


class Pantry(BaseModel):
    items: List[Item] = Field(default_factory=list)


# ---------- Suggestion domain (used by /api/suggest_recipes later) ----------

class SuggestConstraints(BaseModel):
    time_minutes: Optional[int] = Field(None, ge=0)
    mood: Optional[str] = None                 # e.g., "comforting", "light", "spicy"
    diet_conditions: List[str] = Field(default_factory=list)  # e.g., ["vegetarian", "gluten-free"]
    protein_goal_g: Optional[float] = Field(None, ge=0)
    servings: int = Field(1, ge=1)


class Recipe(BaseModel):
    id: str
    title: str
    steps: List[str]
    ingredients: List[Item]
    est_protein_g: Optional[float] = Field(None, ge=0)
    est_kcal: Optional[float] = Field(None, ge=0)
    est_time_minutes: Optional[int] = Field(None, ge=0)
    tags: List[str] = Field(default_factory=list)


class SuggestResponse(BaseModel):
    recipes: List[Recipe]


# ---------- Auditing / events ----------

class InventoryEvent(BaseModel):
    ts: datetime = Field(default_factory=datetime.utcnow)
    type: Literal["ingest", "update", "suggest"]
    payload: dict
    schema_version: int = 1
