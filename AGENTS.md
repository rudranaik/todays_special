# Repository Guidelines

## Project Structure & Module Organization
- `app/`: FastAPI backend and web UI.
  - `app/main.py`: app factory, routes, static/templates.
  - `app/api/`: versioned API routes (`/api/pantry`, `/api/suggest_recipes`, `/api/v1/ingest`).
  - `app/core/`: domain models (`Item`, `Pantry`) and merge logic.
  - `app/services/`: LLM/ASR adapters and JSON repos.
  - `app/web/templates/` and `app/web/static/`: HTML/CSS/JS for the UI.
- `tests/`: `unit/`, `integration/`, and top-level `test_*.py`.
- `data/`: JSON pantry/events when running locally.

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run dev server: `uvicorn app.main:app --reload --port 8002`
- Run tests: `pytest` (configured via `pyproject.toml`)
- Docker (optional): `docker compose up --build pantry`

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indent, descriptive names (`snake_case` for functions/vars, `PascalCase` for classes).
- API routes live under `app/api/v{n}/` and should return pydantic models.
- Keep modules small and cohesive; business logic in `core/` or `services/`, not in route handlers.
- Frontend: vanilla HTML/CSS/JS; keep selectors/classes consistent with existing patterns.

## Testing Guidelines
- Framework: `pytest`.
- Location: place unit tests in `tests/unit/`, integration tests in `tests/integration/`.
- Naming: files start with `test_`, tests named `test_*`.
- Run: `pytest -q`; add focused runs with `-k keyword`.

## Commit & Pull Request Guidelines
- Commits: concise, imperative mood (e.g., "Add grouped pantry sections").
- Scope one logical change per commit. Reference issues with `#123` when relevant.
- PRs: include a short description, screenshots/GIFs for UI changes, and clear test notes (what you ran, outcomes).

## Security & Configuration Tips
- Environment: set variables in `.env` (example):
  - `OPENAI_API_KEY=...` (required for OpenAI-backed features)
  - `OPENAI_MODEL_EXTRACT=gpt-4o-mini`, `OPENAI_MODEL_SUGGEST=gpt-4o-mini`
  - `ITEMSNAP_USE_OPENAI=false` to use offline recipe fallback in dev
- Data files default to `data/`; do not commit secrets or large artifacts.

## Architecture Notes
- Persistence uses JSON repos (`services/repo/json_repo.py`).
- LLM integration lives in `services/llm.py` with a local fallback suggester for reliability.
- Pantry UI groups items by category and lazy-renders non-empty sections.
