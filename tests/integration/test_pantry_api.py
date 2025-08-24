from fastapi.testclient import TestClient
from app.main import create_app

def test_merge_and_get_pantry(tmp_path, monkeypatch):
    # isolate data dir for this test run
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("DATA_DIR", str(d))
    monkeypatch.setenv("PANTRY_FILE", str(d / "pantry.json"))
    monkeypatch.setenv("EVENTS_FILE", str(d / "inventory_log.jsonl"))
    monkeypatch.setenv("OPENAI_API_KEY", "test")  # not used in this test

    app = create_app()
    client = TestClient(app)

    # Merge
    resp = client.post("/api/pantry/merge", json=[{"name":"Tomato","quantity":2,"unit":"g"}])
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["name"] == "Tomato"
    assert body["items"][0]["quantity"] == 2

    # Get
    resp = client.get("/api/pantry")
    assert resp.status_code == 200
    body2 = resp.json()
    assert body2["items"] == body["items"]
