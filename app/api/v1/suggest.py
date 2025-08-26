from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.config import Settings
from app.core.models import Pantry, SuggestConstraints, SuggestResponse, InventoryEvent
from app.services.llm import OpenAIRecipeSuggester, SimpleRecipeSuggester
from app.services.repo.json_repo import JSONPantryRepo, JSONEventRepo
from app.services.metrics import MetricsLogger
import time
from app.services.exceptions import LLMError, RepoError

router = APIRouter(tags=["suggestions"])

# ---- Dependencies ------------------------------------------------------------

def get_settings() -> Settings:
    return Settings()

def get_repos(settings: Settings = Depends(get_settings)):
    return JSONPantryRepo(settings), JSONEventRepo(settings)

def get_suggester(settings: Settings = Depends(get_settings)):
    # Toggle offline fallback with ITEMSNAp_USE_OPENAI=false in .env
    try:
        use_openai = settings.itemsnap_use_openai
    except Exception:
        use_openai = True
    if use_openai:
        return OpenAIRecipeSuggester(settings)
    return SimpleRecipeSuggester()

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
        t0 = time.perf_counter()
        recipes = suggester.suggest(pantry, constraints)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        # best-effort latency log
        try:
            MetricsLogger().log_latency(
                name="suggest_generate",
                duration_ms=dt_ms,
                origin="backend",
                extra={"servings": constraints.servings, "has_constraints": any([
                    constraints.time_minutes is not None,
                    bool(constraints.mood),
                    bool(constraints.diet_conditions),
                    constraints.protein_goal_g is not None,
                ])},
            )
        except Exception:
            pass
    except LLMError as e:
        # Fallback to simple local suggester to avoid breaking the UI
        try:
            fallback = SimpleRecipeSuggester()
            recipes = fallback.suggest(pantry, constraints)
        except Exception:
            # Upstream LLM failure; surface details if fallback also fails
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
