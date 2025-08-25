# Today's Special

Today's Special is a small prototype for managing pantry inventory and discovering recipe ideas.
It provides a FastAPI backend with a lightweight HTML/JS frontend. Key features include:

- **Pantry management** – view, add, and merge pantry items with a visible staging area.
- **Recipe suggestions** – query an OpenAI‑powered endpoint for recipe ideas based on pantry contents and constraints.
- **Voice ingest** – record audio in the browser, transcribe with Whisper, and extract items for staging.

## Running locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then visit `http://localhost:8000/` in a browser to use the web UI.

## Testing

Run the test suite with:

```bash
pytest
```

(Dependencies are required for tests to pass.)
