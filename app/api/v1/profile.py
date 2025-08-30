from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.config import Settings
from app.core.models import UserProfile
from app.services.repo.profile_repo import JSONUserProfileRepo
from app.services.exceptions import RepoError

router = APIRouter(tags=["profile"])

# ---- Dependencies ------------------------------------------------------------

def get_settings() -> Settings:
    return Settings()

def get_profile_repo(settings: Settings = Depends(get_settings)) -> JSONUserProfileRepo:
    return JSONUserProfileRepo(settings)

# ---- Business logic ----------------------------------------------------------

def calculate_macro_goals(profile: UserProfile) -> UserProfile:
    """Calculate macro goals based on user profile."""
    # Mifflin-St Jeor equation for BMR
    if profile.gender == "male":
        s = 5
    else:
        s = -161
    
    bmr = (10 * profile.weight) + (6.25 * profile.height) - (5 * profile.age) + s
    
    # TDEE (assuming sedentary activity level)
    tdee = bmr * 1.2
    
    # Macro distribution (40% carbs, 30% protein, 30% fat)
    calories = tdee
    protein = (tdee * 0.30) / 4
    carbohydrates = (tdee * 0.40) / 4
    fats = (tdee * 0.30) / 9
    
    profile.macro_goals.calories = round(calories)
    profile.macro_goals.protein = round(protein)
    profile.macro_goals.carbohydrates = round(carbohydrates)
    profile.macro_goals.fats = round(fats)

    # Distribute macros across meals
    num_meals = len(profile.meals)
    if num_meals > 0:
        for meal in profile.meals:
            meal.calories = round(calories / num_meals)
            meal.protein = round(protein / num_meals)
            meal.carbohydrates = round(carbohydrates / num_meals)
            meal.fats = round(fats / num_meals)

    return profile

# ---- Routes ------------------------------------------------------------------

@router.get("/api/v1/profile", response_model=UserProfile)
def get_profile(repo: JSONUserProfileRepo = Depends(get_profile_repo)):
    try:
        profile = repo.load()
        if not profile:
            # Create a default profile if one doesn't exist
            profile = UserProfile(
                user_name="",
                age=30,
                gender="male",
                height=175,
                weight=70,
                country="",
            )
            profile = calculate_macro_goals(profile)
            repo.save(profile)
        return profile
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/v1/profile", response_model=UserProfile)
def update_profile(profile: UserProfile, repo: JSONUserProfileRepo = Depends(get_profile_repo)):
    try:
        # Recalculate macro goals when the profile is updated
        recalculated_profile = calculate_macro_goals(profile)
        repo.save(recalculated_profile)
        return recalculated_profile
    except RepoError as e:
        raise HTTPException(status_code=500, detail=str(e))
