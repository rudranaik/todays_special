from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings
from app.core.merge import apply_merge
from app.core.models import Item, Pantry, InventoryEvent
from app.services.exceptions import RepoError
from app.services.repo.json_repo import JSONPantryRepo, JSONEventRepo

router = APIRouter(tags=["pantry"])

# ---- DI helpers --------------------------------------------------------------

def get_settings() -> Settings:
    return Settings()

def get_repos(settings: Settings = Depends(get_settings)):
    return JSONPantryRepo(settings), JSONEventRepo(settings)

# ---- Routes ------------------------------------------------------------------

@router.get("/api/pantry", response_model=Pantry)
def get_pantry(repos = Depends(get_repos)):
    pantry_repo, _event_repo = repos
    try:
        return pantry_repo.load()
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/pantry", response_model=Pantry, status_code=status.HTTP_200_OK)
def replace_pantry(pantry: Pantry, repos = Depends(get_repos)):
    pantry_repo, event_repo = repos
    try:
        pantry_repo.save(pantry)
        event_repo.append(InventoryEvent(type="update", payload={"mode": "replace", "items": [i.dict() for i in pantry.items]}))
        return pantry
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/pantry/merge", response_model=Pantry, status_code=status.HTTP_200_OK)
def merge_into_pantry(items: List[Item], repos = Depends(get_repos)):
    pantry_repo, event_repo = repos
    try:
        current = pantry_repo.load()
        merged = apply_merge(current, items)
        pantry_repo.save(merged)
        event_repo.append(InventoryEvent(type="update", payload={"mode": "merge", "delta": [i.dict() for i in items]}))
        return merged
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))
