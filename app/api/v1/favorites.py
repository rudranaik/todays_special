from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from app.config import Settings
from app.core.models import Recipe, SuggestResponse
from app.services.repo.json_repo import JSONFavoritesRepo
from app.services.exceptions import RepoError

router = APIRouter(tags=["favorites"])


def get_settings() -> Settings:
    return Settings()


def get_repo(settings: Settings = Depends(get_settings)):
    return JSONFavoritesRepo(settings)


def _device_id_or_400(request: Request) -> str:
    did = request.headers.get("X-Device-Id")
    if not did:
        raise HTTPException(status_code=400, detail="Missing X-Device-Id header")
    return did


@router.get("/api/v1/favorites", response_model=SuggestResponse)
def list_favorites(repo: JSONFavoritesRepo = Depends(get_repo), request: Request = None):
    device_id = _device_id_or_400(request)
    try:
        recipes = repo.load(device_id)
        return SuggestResponse(recipes=recipes)
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/favorites", response_model=SuggestResponse)
def add_favorite(recipe: Recipe, repo: JSONFavoritesRepo = Depends(get_repo), request: Request = None):
    device_id = _device_id_or_400(request)
    try:
        repo.add(device_id, recipe)
        recipes = repo.load(device_id)
        return SuggestResponse(recipes=recipes)
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/favorites/{recipe_id}")
def remove_favorite(recipe_id: str, repo: JSONFavoritesRepo = Depends(get_repo), request: Request = None):
    device_id = _device_id_or_400(request)
    try:
        removed = repo.remove(device_id, recipe_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Recipe not found in favorites")
        return {"ok": True}
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))

