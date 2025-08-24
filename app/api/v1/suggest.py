from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.config import Settings
from app.core.models import Pantry, SuggestConstraints, SuggestResponse, InventoryEvent
from app.services.llm import OpenAIRecipeSuggester
from app.services.repo.json_repo import JSONPantryRepo, JSONEventRepo
from app.services.exceptions import LLMError, RepoError

router = APIRouter(tags=["suggestions"])

# ---- Dependencies ------------------------------------------------------------

def get_settings() -> Settings:
    return Settings()

def get_repos(settings: Settings = Depends(get_settings)):
    return JSONPantryRepo(settings), JSONEventRepo(settings)

def get_suggester(settings: Settings = Depends(get_settings)):
    return OpenAIRecipeSuggester(settings)

# ---- Route ------------------------------------------------------------------

@router.post("/api/suggest_recipes", response_model=SuggestResponse)
def suggest_recipes(
    constraints: SuggestConstraints,
    suggester: OpenAIRecipeSuggester = Depends(get_suggester),
    repos = Depends(get_repos),
):
    pantry_repo, event_repo = repos
    try:
        pantry: Pantry = pantry_repo.load()
    except RepoError as e:
        # Storage failure
        raise HTTPException(status_code=500, detail=str(e))

    try:
        recipes = suggester.suggest(pantry, constraints)
    except LLMError as e:
        # Upstream LLM failure; surface details; no fallback
        raise HTTPException(status_code=502, detail=str(e))

    # Log the event (best-effort; if it fails, still return suggestions)
    try:
        event_repo.append(
            InventoryEvent(
                type="suggest",
                payload={
                    "constraints": constraints.dict(),
                    "recipe_count": len(recipes),
                },
            )
        )
    except RepoError:
        # Don’t fail the request on log errors
        pass

    return SuggestResponse(recipes=recipes)
