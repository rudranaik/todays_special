from __future__ import annotations

import json
from typing import List
from pydantic import BaseModel
from .exceptions import LLMError
from app.core.models import Item, Pantry, Recipe, SuggestConstraints
from app.config import Settings

# OpenAI SDK v1+
try:
    from openai import OpenAI
except Exception as e:  # pragma: no cover
    raise LLMError("Failed to import OpenAI SDK. Install with `pip install openai`") from e


class ItemExtractor(BaseModel):
    """
    Interface-like base to keep types clear. Concrete impl below.
    """
    def extract(self, transcript: str) -> List[Item]:  # pragma: no cover - interface
        raise NotImplementedError


class RecipeSuggester(BaseModel):
    def suggest(self, pantry: Pantry, constraints: SuggestConstraints) -> List[Recipe]:  # pragma: no cover
        raise NotImplementedError


class OpenAIItemExtractor(ItemExtractor):
    _client: OpenAI
    _model: str

    def __init__(self, settings: Settings):
        super().__init__()
        try:
            self._client = OpenAI(api_key=settings.openai_api_key)
        except Exception as e:
            raise LLMError("Could not initialize OpenAI client") from e
        self._model = settings.openai_model_extract

    def extract(self, transcript: str) -> List[Item]:
        """
        Extract items as JSON with optional category from a fixed set.
        """
        try:
            # Use responses API with JSON schema if you prefer; keeping it simple here.
            categories = [
                "Grains & Cereals",
                "Legumes & Pulses",
                "Vegetables - Leafy greens",
                "Vegetables - Root & tubers",
                "Vegetables - Cruciferous",
                "Vegetables - Others",
                "Fruits",
                "Herbs & Spices",
                "Oils & Fats",
                "Dairy & Alternatives",
                "Meat & Poultry",
                "Seafood",
                "Eggs",
                "Nuts & Seeds",
                "Condiments & Sauces",
                "Sweeteners",
                "Baking & Essentials",
                "Snacks & Miscellaneous",
            ]
            allowed = ", ".join(categories)
            prompt = (
                "Extract grocery/pantry items from this transcript (may be multilingual). "
                "If unsure about quantity, set it to 1. Do not invent items. "
                "Return ONLY a strict JSON array where each item is: "
                '{"name": str, "quantity"?: number, "unit"?: str, "category"?: str}. '
                "If you can classify the item, set 'category' to one of these exactly: "
                f"{allowed}. Otherwise omit category.\n\n"
                "Examples: spinach -> 'Vegetables - Leafy greens'; potatoes -> 'Vegetables - Root & tubers'; "
                "chili powder -> 'Herbs & Spices'; olive oil -> 'Oils & Fats'; basmati rice -> 'Grains & Cereals'.\n\n"
                f"Transcript:\n{transcript}"
            )
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": "You extract shopping items as strict JSON."},
                          {"role": "user", "content": prompt}],
                # temperature=0,
            )
            content = resp.choices[0].message.content or "[]"
            data = json.loads(content)
            items: List[Item] = []
            for row in data:
                items.append(Item(
                    name=row["name"],
                    quantity=float(row.get("quantity") or 0),
                    unit=row.get("unit"),
                    category=row.get("category"),
                ))
            return items
        except Exception as e:
            # No fallback: bubble details up
            raise LLMError(f"OpenAI extract failed: {e}") from e


class OpenAIRecipeSuggester(RecipeSuggester):
    _client: OpenAI
    _model: str

    def __init__(self, settings: Settings):
        super().__init__()
        try:
            self._client = OpenAI(api_key=settings.openai_api_key)
        except Exception as e:
            raise LLMError("Could not initialize OpenAI client") from e
        self._model = settings.openai_model_suggest

    def suggest(self, pantry: Pantry, constraints: SuggestConstraints) -> List[Recipe]:
        try:
            pantry_min = [
                {"name": it.name, "quantity": it.quantity, "unit": it.unit}
                for it in pantry.items
            ]
            prompt = (
                "You are the world's best grandma, and cook the best food with whatever you have."
                "Given this pantry and constraints your grandkids have, propose 3 recipes with instructions"
                "listed very logvingly. Make sure to only use the available ingredients in the pantry,"
                "and strictly adhere to the constrainst, else your grandkids will not be able to cook it."
                "Also know that these kids are very new to cooking, so they won't know the right moment"
                "to add ingredients. So you'll have to give them relatable milestones like smell, visibility, etc."
                "so that they can know when to follow the next step." 
                "Give you inputs as a strict JSON in the following format:\n"
                "Schema: {\"recipes\":[{\"id\": str, \"title\": str, \"steps\": [str], "
                "\"ingredients\":[{\"name\": str, \"quantity\": number?, \"unit\": str?}], "
                "\"est_protein_g\": number?, \"est_kcal\": number?, "
                "\"est_time_minutes\": number?, \"tags\":[str]}]}\n\n"
                f"Pantry: {json.dumps(pantry_min)}\n"
                f"Constraints: {constraints.json()}\n"
                "Return ONLY the JSON object; no commentary."
            )
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": "You are a precise recipe generator returning strict JSON."},
                          {"role": "user", "content": prompt}],
                # temperature=0.2,
            )
            content = resp.choices[0].message.content or "{\"recipes\":[]}"
            data = json.loads(content)
            out: List[Recipe] = []
            for r in data.get("recipes", []):
                items = [Item(name=i["name"], quantity=float(i.get("quantity") or 0), unit=i.get("unit"))
                         for i in r.get("ingredients", [])]
                out.append(Recipe(
                    id=r["id"],
                    title=r["title"],
                    steps=list(r.get("steps", [])),
                    ingredients=items,
                    est_protein_g=r.get("est_protein_g"),
                    est_kcal=r.get("est_kcal"),
                    est_time_minutes=r.get("est_time_minutes"),
                    tags=list(r.get("tags", [])),
                ))
            return out
        except Exception as e:
            raise LLMError(f"OpenAI suggest failed: {e}") from e
