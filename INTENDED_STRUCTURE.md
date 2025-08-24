# This file details the intended structure behind making this prototype ready for scaling to production

app/
  api/
    __init__.py
    v1/
      __init__.py
      ingest.py           # HTTP/WebSocket endpoints to accept speech/audio & item JSON
      pantry.py           # CRUD & merge
      suggest.py          # recipe suggestion endpoint
  core/
    __init__.py
    models.py             # Pydantic models: Item, Pantry, Event, SuggestConstraints, Recipe, etc.
    parsing.py            # free-text to items (fallback), normalizers
    merge.py              # deterministic pantry merge rules
    suggest.py            # pure suggestion orchestrator (no HTTP here)
  services/
    __init__.py
    asr.py                # faster-whisper wrapper (constructor, transcribe_stream, transcribe_file)
    llm.py                # OpenAI client adapter with interfaces + fallback
    repo.py               # Repository interfaces + implementations (JSON now, DB later)
      json_repo.py        # JSON-backed pantry + event log (current)
      sql_repo.py         # placeholder for future SQLModel/SQLAlchemy
  web/
    static/
      app.css
      app.js
    templates/
      index.html          # (voice page)
      review.html         # (review page)
  config.py               # Pydantic settings for envs (dev/stage/prod)
  main.py                 # FastAPI app factory; mounts routers & static; health checks
  __init__.py

tests/
  unit/
    test_parsing.py
    test_merge.py
    test_models.py
  integration/
    test_ingest_api.py
    test_pantry_api.py
    test_suggest_api.py

docker/
  Dockerfile
  gunicorn_conf.py
  compose.yml

scripts/
  dev_run.sh
  seed_demo_data.py
