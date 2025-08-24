"""
Self-contained FastAPI app that lets you:
1) POST an ingredient JSON from your speech→LLM step ("ingest").
2) Open /review to edit items in a clean UI (name, qty, unit, +/- , delete).
3) Click **Update Pantry** to MERGE into a persistent pantry (data/pantry.json)
   and append an event to data/inventory_log.jsonl.
4) Button to jump to the voice capture app (local_2) to add more by voice.
5) Suggest recipes from pantry + constraints (time, mood, diet tags, protein goal, servings),
   with macronutrient estimates. Uses OpenAI if configured; otherwise a lightweight fallback.

Run:
  uvicorn review_ui:app --reload --port 8001
"""

from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, validator

# Load .env if present
from dotenv import load_dotenv, find_dotenv
_dotenv_path = find_dotenv(filename=".env", usecwd=True)
if _dotenv_path:
    load_dotenv(_dotenv_path, override=True)

# Optional OpenAI client for recipe suggestions
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

_openai_client = None
SUGGEST_MODEL = None
if OpenAI is not None and os.getenv("OPENAI_API_KEY"):
    _openai_client = OpenAI()
    # fall back to your extraction model if provided
    SUGGEST_MODEL = os.getenv("SUGGEST_MODEL", os.getenv("ITEMSNAP_MODEL", "gpt-5-nano"))

# ------------------------
# Data models
# ------------------------

class Ingredient(BaseModel):
    name: str = Field(..., description="Human-friendly ingredient name")
    quantity: float = Field(..., description="Numeric quantity; can be fractional")
    unit: Optional[str] = Field(None, description="Unit like pieces, cups, g, ml, lbs")

    @validator("name")
    def clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v

class IngestPayload(BaseModel):
    items: List[Ingredient]

class PantryState(BaseModel):
    items: List[Ingredient]
    updated_at: float

class SuggestConstraints(BaseModel):
    time_minutes: int = Field(30, ge=1, le=240)
    mood: Literal["healthy", "indulgent", "open"] = "open"
    diet_conditions: List[str] = Field(default_factory=list)
    protein_goal_g: Optional[float] = Field(None, ge=0)
    servings: int = Field(1, ge=1, le=12, description="Number of people to serve")

class SuggestRequest(BaseModel):
    items: List[Ingredient]
    constraints: SuggestConstraints

class Recipe(BaseModel):
    title: str
    time_minutes: int
    mood: str
    diet_tags: List[str]
    ingredients_used: List[str]
    steps: List[str]
    protein_g: float
    carbs_g: float
    fat_g: float
    calories_kcal: float

class SuggestResponse(BaseModel):
    recipes: List[Recipe]

# ------------------------
# App setup
# ------------------------

app = FastAPI(title="Ingredients Review UI", version="0.3.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path("data")
PANTRY_FILE = DATA_DIR / "pantry.json"
LOG_FILE = DATA_DIR / "inventory_log.jsonl"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Link back to the voice capture app (local_2)
INGEST_BASE = os.getenv("INGEST_BASE", "http://127.0.0.1:8000")

# In-memory last batch (so /review can render instantly after /api/ingest)
_LAST_BATCH: List[Ingredient] = []

# ------------------------
# Merge helpers
# ------------------------

def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _merge_pantry(existing: List[Ingredient], incoming: List[Ingredient]) -> List[Ingredient]:
    """Merge by (name, unit) key; sum quantities when unit matches.
    - Names/units are normalized for matching but we keep original casing of the first seen item.
    - Quantities are clamped to >= 0.
    """
    index: dict[tuple[str, str], Ingredient] = {}

    def clamp(q: float) -> float:
        try:
            return max(0.0, float(q))
        except Exception:
            return 0.0

    for it in existing:
        key = (_norm(it.name), _norm(it.unit))
        index[key] = Ingredient(
            name=it.name.strip(),
            quantity=clamp(it.quantity),
            unit=(it.unit.strip() if it.unit else None),
        )

    for it in incoming:
        key = (_norm(it.name), _norm(it.unit))
        if key in index:
            index[key].quantity = round(float(index[key].quantity) + clamp(it.quantity), 6)
        else:
            index[key] = Ingredient(
                name=it.name.strip(),
                quantity=clamp(it.quantity),
                unit=(it.unit.strip() if it.unit else None),
            )

    return list(index.values())

# ------------------------
# Suggestion helper
# ------------------------

SUGGEST_SYS = (
    "You are a culinary expert. You will receive pantry items and client constraints. "
    "Return exactly 3 realistic recipes using ONLY the pantry items. "
    "Scale ingredient amounts to the TARGET SERVINGS provided in the constraints. "
    "Keep total time under the constraint and COUNT ALL PRE-PREPARATION (washing, trimming, chopping, parboiling) inside that time. "
    "Write detailed, concise, step-by-step instructions. "
    "IMPORTANT: The FIRST step must be a single line starting with 'Prep time note:' that states the approximate minutes of pre-preparation "
    "and the main prep actions (e.g., 'Prep time note: approximately 7–8 minutes (trim beans; dice onion; mince garlic)'). "
    "Estimate macronutrients conservatively. "
    "Output only JSON conforming to the provided schema."
)

def _suggest_with_openai(payload: SuggestRequest) -> SuggestResponse:
    assert _openai_client is not None and SUGGEST_MODEL
    target_servings = getattr(payload.constraints, "servings", 1)

    prompt = {
        "pantry": [i.dict() for i in payload.items],
        "constraints": payload.constraints.dict(),
        "schema": Recipe.schema(),
        "notes": (
            "Return exactly 3 recipes in key 'recipes'. "
            "Scale ingredient quantities to SERVE the target number of people from constraints "
            f"(target_servings={target_servings}). "
            "Put the pre-prep disclosure as the FIRST step starting with 'Prep time note:'. "
            "Units in grams for macros and kcal for calories."
        ),
    }

    chat = _openai_client.chat.completions.create(
        model=SUGGEST_MODEL,
        messages=[
            {"role": "system", "content": SUGGEST_SYS},
            {"role": "user", "content": json.dumps(prompt)},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(chat.choices[0].message.content)
    return SuggestResponse(**data)

def _suggest_fallback(payload: SuggestRequest) -> SuggestResponse:
    # Super-simplified fallback: assemble salad/stir-fry/omelette style dishes
    names = [i.name for i in payload.items]
    base1 = next((n for n in names if "egg" in n.lower()), "Pantry Omelette")
    base2 = next((n for n in names if "rice" in n.lower()), "Quick Stir-Fry Rice")
    base3 = next((n for n in names if "cucumber" in n.lower() or "beans" in n.lower()), "Crunchy Salad Bowl")
    recipes = [
        Recipe(
            title=str(base1),
            time_minutes=min(20, payload.constraints.time_minutes),
            mood=payload.constraints.mood,
            diet_tags=payload.constraints.diet_conditions,
            ingredients_used=names[:6],
            steps=[
                "Prep time note: approximately 5–6 minutes (crack eggs; dice onion; slice chili).",
                "Whisk eggs with salt and pepper.",
                "Sauté aromatics in oil.",
                "Fold in pantry veggies and cook until set.",
            ],
            protein_g=25.0,
            carbs_g=5.0,
            fat_g=18.0,
            calories_kcal=290.0,
        ),
        Recipe(
            title=str(base2),
            time_minutes=min(25, payload.constraints.time_minutes),
            mood=payload.constraints.mood,
            diet_tags=payload.constraints.diet_conditions,
            ingredients_used=names[:8],
            steps=[
                "Prep time note: approximately 8–10 minutes (rinse rice if raw; dice vegetables).",
                "Cook rice (or use leftover).",
                "Stir-fry with oil and veg; season and serve.",
            ],
            protein_g=18.0,
            carbs_g=55.0,
            fat_g=12.0,
            calories_kcal=430.0,
        ),
        Recipe(
            title=str(base3),
            time_minutes=min(15, payload.constraints.time_minutes),
            mood=payload.constraints.mood,
            diet_tags=payload.constraints.diet_conditions,
            ingredients_used=names[:5],
            steps=[
                "Prep time note: approximately 6–7 minutes (wash; chop vegetables).",
                "Make dressing, toss, and rest 5 min.",
            ],
            protein_g=10.0,
            carbs_g=12.0,
            fat_g=14.0,
            calories_kcal=230.0,
        ),
    ]
    return SuggestResponse(recipes=recipes)

# ------------------------
# API endpoints
# ------------------------

@app.post("/api/ingest")
async def ingest(payload: IngestPayload):
    global _LAST_BATCH
    _LAST_BATCH = payload.items
    event = {
        "ts": datetime.utcnow().isoformat(),
        "type": "ingest",
        "items": [i.dict() for i in payload.items],
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return RedirectResponse(url="/review", status_code=303)

@app.get("/api/last_batch")
async def last_batch():
    if not _LAST_BATCH:
        raise HTTPException(404, "No batch ingested yet. POST to /api/ingest first.")
    return {"items": [i.dict() for i in _LAST_BATCH]}

@app.get("/api/pantry")
async def read_pantry():
    if not PANTRY_FILE.exists():
        return {"items": [], "updated_at": 0}
    data = json.loads(PANTRY_FILE.read_text(encoding="utf-8"))
    return data

@app.get("/api/config")
async def config():
    return {"ingest_base": INGEST_BASE}

@app.post("/api/update_pantry")
async def update_pantry(state: PantryState, merge: bool = True):
    global _LAST_BATCH

    existing: List[Ingredient] = []
    if PANTRY_FILE.exists():
        try:
            raw = json.loads(PANTRY_FILE.read_text(encoding="utf-8"))
            existing = [Ingredient(**d) for d in raw.get("items", [])]
        except Exception:
            existing = []

    final_items = _merge_pantry(existing, state.items) if merge else state.items

    with PANTRY_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {"items": [i.dict() for i in final_items], "updated_at": state.updated_at},
            f,
            ensure_ascii=False,
            indent=2,
        )

    event = {
        "ts": datetime.utcnow().isoformat(),
        "type": "update_pantry",
        "strategy": "merge" if merge else "overwrite",
        "items": [i.dict() for i in state.items],
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    _LAST_BATCH = []

    return {"ok": True, "items": [i.dict() for i in final_items]}

@app.post("/api/suggest_recipes", response_model=SuggestResponse)
async def suggest_recipes(req: SuggestRequest):
    try:
        if _openai_client is not None and SUGGEST_MODEL:
            out = _suggest_with_openai(req)
        else:
            out = _suggest_fallback(req)
        # Log
        event = {
            "ts": datetime.utcnow().isoformat(),
            "type": "suggest",
            "constraints": req.constraints.dict(),
            "count": len(out.recipes),
        }
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return JSONResponse(content=out.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------
# Review UI
# ------------------------

REVIEW_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Review Your Ingredients</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root { --bg:#f8faf9; --card:#ffffff; --muted:#6b7280; --text:#0f172a; --green:#16a34a; --red:#ef4444; --border:#e5e7eb; --indigo:#4f46e5; }
    * { box-sizing: border-box; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
    body { margin:0; background:var(--bg); color:var(--text); }
    .container { max-width: 1040px; margin: 28px auto; padding: 0 16px; }
    h1 { margin: 0 0 6px; font-size: 28px; }
    .sub { color: var(--muted); margin-bottom: 16px; }
    .card { background: var(--card); border:1px solid var(--border); border-radius: 14px; padding: 14px 16px; display:flex; align-items:center; gap:12px; }
    .stack { display:flex; flex-direction: column; gap: 14px; }
    .name { flex: 1; }
    .name input { width: 100%; border:1px solid var(--border); border-radius: 10px; padding: 12px 12px; font-size: 15px; }
    .qtybox { display:flex; align-items:center; gap:10px; }
    .qty { min-width: 58px; text-align:center; font-weight: 700; font-size: 18px; }
    .unit { color: var(--muted); font-size: 12px; }
    .btn { border:1px solid var(--border); background:#fff; padding:8px 10px; border-radius:12px; font-weight:600; cursor:pointer; }
    .btn:hover { background:#f3f4f6; }
    .btn.icon { width:36px; height:36px; display:flex; align-items:center; justify-content:center; font-size:18px; }
    .row-left { display:flex; align-items:center; gap:12px; flex: 1; }
    .x { color: var(--red); font-weight:700; }
    .footer { display:flex; gap: 12px; margin: 28px 0; align-items:center; flex-wrap: wrap; }
    .primary { background: var(--green); color:#fff; border:none; }
    .danger { background: #fff; color: var(--red); border:1px solid #fecaca; }
    .pill { border:1px solid var(--border); border-radius:12px; padding:4px 8px; }
    .unit-input { width: 88px; border:1px solid var(--border); border-radius:10px; padding:8px; }
    .spacer { flex: 1; }

    /* Controls */
    .controls { display:grid; grid-template-columns: repeat(6, minmax(140px, 1fr)); gap:12px; align-items:end; margin-top: 18px; }
    .controls label { font-size: 12px; color: var(--muted); display:block; margin-bottom:4px; }
    .controls input, .controls select { width:100%; padding:10px; border:1px solid var(--border); border-radius:10px; }

    /* Diet chips */
    .chips-wrap { grid-column: span 2; }
    .chips { display:flex; flex-wrap: wrap; gap:8px; }
    .chip { padding:8px 12px; border:1px solid var(--border); border-radius:999px; background:#fff; cursor:pointer; }
    .chip.active { border-color: var(--indigo); background:#eef2ff; }

    /* Servings stepper */
    .servings-input { display:inline-flex; align-items:center; border:1px solid var(--border); border-radius:10px; overflow:hidden; }
    .servings-input input { width:60px; text-align:center; border:none; padding:10px 0; }
    .servings-input button { width:36px; height:36px; border:none; background:#f3f4f6; font-size:18px; cursor:pointer; }
    .servings-input button:active { transform: translateY(1px); }

    /* Recipe grid + card polish */
    .recipes { margin: 18px 0 36px; display:grid; grid-template-columns: repeat(auto-fill, minmax(300px,1fr)); gap:16px; }
    .recipe-card { background:#fff; border:1px solid var(--border); border-radius:16px; box-shadow: 0 6px 16px rgba(20,24,40,0.04); overflow:hidden; display:flex; flex-direction:column; }
    .card-header { padding:16px 16px 0 16px; }
    .card-title { font-weight: 800; font-size: 18px; color:#0f172a; line-height:1.2; }
    .card-sub { color:#475569; font-size: 13px; margin-top: 6px; display:flex; gap:10px; flex-wrap:wrap; }
    .badge { font-size:12px; padding:4px 8px; border-radius:999px; background:#f1f5f9; }

    .prepbox { background:#fff7ed; border-top:1px dashed #fdba74; border-bottom:1px dashed #fdba74; padding:12px 16px; }
    .prepbox-title { font-weight:700; color:#9a3412; margin-bottom:4px; }
    .prepbox-text { color:#7c2d12; font-size:14px; }

    .card-body { padding:12px 16px 16px 16px; display:flex; flex-direction:column; gap:12px; }
    .section-title { font-weight:700; color:#1f2937; font-size:14px; margin-top: 4px; }
    .uses { color:#475569; font-size: 13px; }
    .steps { margin:0; padding-left: 18px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Review Your Ingredients</h1>
    <div class="sub">Edit ingredient names and adjust quantities as needed</div>

    <div id="list" class="stack"></div>

    <div class="footer">
      <button id="updateBtn" class="btn primary">Update Pantry</button>
      <button id="discardBtn" class="btn danger">Discard Changes</button>
      <div class="spacer"></div>
      <button id="voiceBtn" class="btn">➕ Add More by Voice</button>
      <span id="status" class="pill"></span>
    </div>

    <h3>Recipe Suggestions</h3>
    <div class="controls">
      <div>
        <label>Time to cook (min)</label>
        <input type="number" id="timeMin" value="30" min="1" max="240" />
      </div>
      <div>
        <label>Mood</label>
        <select id="mood">
          <option value="healthy">Healthy</option>
          <option value="indulgent">Indulgent</option>
          <option value="open" selected>Open</option>
        </select>
      </div>

      <!-- Diet conditions as chips -->
      <div class="chips-wrap">
        <label>Diet conditions</label>
        <div id="dietChips" class="chips">
          <button type="button" data-value="Keto" class="chip">Keto</button>
          <button type="button" data-value="Atkins" class="chip">Atkins</button>
          <button type="button" data-value="Low carb" class="chip">Low carb</button>
          <button type="button" data-value="Diabetic friendly" class="chip">Diabetic friendly</button>
          <button type="button" data-value="Vegetarian" class="chip">Vegetarian</button>
          <button type="button" data-value="Vegan" class="chip">Vegan</button>
          <button type="button" data-value="Gluten free" class="chip">Gluten free</button>
          <button type="button" data-value="High protein" class="chip">High protein</button>
        </div>
      </div>

      <div>
        <label>Protein goal (g)</label>
        <input type="number" id="proteinGoal" placeholder="e.g., 40" min="0" />
      </div>

      <div>
        <label>Serves</label>
        <div class="servings-input">
          <button type="button" id="servDec" aria-label="decrease">−</button>
          <input id="servings" type="number" min="1" max="12" value="1">
          <button type="button" id="servInc" aria-label="increase">+</button>
        </div>
      </div>

      <div>
        <button id="suggestBtn" class="btn primary">Suggest Recipes</button>
      </div>
    </div>

    <div id="recipes" class="recipes"></div>
  </div>

<script>
  let items = [];
  let INGEST_BASE = null;

  function fmt(n){ return Number(n).toString(); }

  function render(){
    const mount = document.getElementById('list');
    mount.innerHTML = '';
    items.forEach((it, idx) => {
      const row = document.createElement('div');
      row.className = 'card';

      const del = document.createElement('button');
      del.className = 'btn icon x';
      del.textContent = '×';
      del.onclick = () => { items.splice(idx,1); render(); };

      const nameWrap = document.createElement('div');
      nameWrap.className = 'name';
      const nameInput = document.createElement('input');
      nameInput.value = it.name || '';
      nameInput.oninput = (e)=>{ it.name = e.target.value };
      nameWrap.appendChild(nameInput);

      const qtyBox = document.createElement('div');
      qtyBox.className = 'qtybox';
      const minus = document.createElement('button'); minus.className='btn icon'; minus.textContent='−';
      minus.onclick = ()=>{ it.quantity = Math.max(0, parseFloat(it.quantity||0) - 1); render(); };
      const qty = document.createElement('div'); qty.className='qty'; qty.textContent = fmt(it.quantity ?? 0);
      const plus = document.createElement('button'); plus.className='btn icon'; plus.textContent='+';
      plus.onclick = ()=>{ it.quantity = parseFloat(it.quantity||0) + 1; render(); };
      const unit = document.createElement('input'); unit.className='unit-input'; unit.placeholder='unit'; unit.value = it.unit || '';
      unit.oninput=(e)=>{ it.unit = e.target.value };

      qtyBox.appendChild(minus); qtyBox.appendChild(qty); qtyBox.appendChild(plus);
      qtyBox.appendChild(unit);

      const left = document.createElement('div');
      left.className = 'row-left';
      left.appendChild(del); left.appendChild(nameWrap);

      row.appendChild(left);
      row.appendChild(qtyBox);
      mount.appendChild(row);
    });
  }

  async function load(){
    // load config for the link back to voice app
    try {
      const c = await fetch('/api/config');
      const cfg = await c.json();
      INGEST_BASE = cfg.ingest_base || null;
    } catch(e) { INGEST_BASE = null; }

    try{
      const r = await fetch('/api/last_batch');
      if(!r.ok) throw new Error('No batch to review');
      const data = await r.json();
      items = data.items || [];
    }catch(e){
      // fall back to existing pantry if no batch
      const r2 = await fetch('/api/pantry');
      const data2 = await r2.json();
      items = data2.items || [];
    }
    render();
  }

  // Diet chips toggle
  const selectedDiets = new Set();
  document.addEventListener('click', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('chip')) {
      const v = e.target.dataset.value;
      if (selectedDiets.has(v)) { selectedDiets.delete(v); e.target.classList.remove('active'); }
      else { selectedDiets.add(v); e.target.classList.add('active'); }
    }
  });

  // Servings stepper
  const servInput = (() => document.getElementById('servings'))();
  document.getElementById('servDec').onclick = () => { const v = Math.max(1, (parseInt(servInput.value||'1',10)-1)); servInput.value = v; };
  document.getElementById('servInc').onclick = () => { const v = Math.min(12, (parseInt(servInput.value||'1',10)+1)); servInput.value = v; };

  // Suggest click (single, canonical handler)
  document.getElementById('suggestBtn').onclick = async () => {
    if (!items.length) { alert('No items in list'); return; }
    const payload = {
      items,
      constraints: {
        time_minutes: Number(document.getElementById('timeMin').value || 30),
        mood: document.getElementById('mood').value,
        diet_conditions: Array.from(selectedDiets),
        protein_goal_g: document.getElementById('proteinGoal').value ? Number(document.getElementById('proteinGoal').value) : null,
        servings: parseInt(servInput.value || '1', 10)
      }
    };
    const btn = document.getElementById('suggestBtn');
    btn.disabled = true; btn.textContent = 'Thinking…';
    try {
      const r = await fetch('/api/suggest_recipes', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      renderRecipes(data.recipes || []);
    } catch (e) {
      alert('Suggest failed: ' + e);
    } finally {
      btn.disabled = false; btn.textContent = 'Suggest Recipes';
    }
  };

  function renderRecipes(recipes) {
    const root = document.getElementById('recipes');
    root.innerHTML = '';
    recipes.forEach(r => root.appendChild(renderRecipeCard(r)));
  }

  function renderRecipeCard(r) {
    const card = document.createElement('div'); card.className = 'recipe-card';

    // Header
    const header = document.createElement('div'); header.className = 'card-header';
    const title = document.createElement('div'); title.className = 'card-title';
    title.textContent = r.title || 'Recipe';
    const sub = document.createElement('div'); sub.className = 'card-sub';

    const timeBadge = makeBadge(`~${r.time_minutes ?? 30} min`);
    const tags = Array.isArray(r.diet_tags) ? r.diet_tags : [];
    const tagsBadge = makeBadge(tags.slice(0,3).join(' • ') || 'No diet tags');
    const macrosBadge = makeBadge(`Protein ${r.protein_g ?? 0}g • Carbs ${r.carbs_g ?? 0}g • Fat ${r.fat_g ?? 0}g • ${r.calories_kcal ?? 0} kcal`);
    sub.append(timeBadge, tagsBadge, macrosBadge);

    header.append(title, sub);
    card.appendChild(header);

    // Pull out pre-prep if the first step is a "Prep time note"
    let prepLine = null;
    let steps = Array.isArray(r.steps) ? [...r.steps] : [];
    if (steps.length && /^prep\\s*time\\s*note/i.test(steps[0])) {
      prepLine = steps.shift();
    }

    if (prepLine) {
      const prep = document.createElement('div'); prep.className = 'prepbox';
      const h = document.createElement('div'); h.className = 'prepbox-title'; h.textContent = 'Pre-prep';
      const p = document.createElement('div'); p.className = 'prepbox-text'; p.textContent = prettifyPrep(prepLine);
      prep.append(h, p);
      card.appendChild(prep);
    }

    // Body sections
    const body = document.createElement('div'); body.className = 'card-body';

    const uses = document.createElement('div'); uses.className = 'uses';
    const used = Array.isArray(r.ingredients_used) ? r.ingredients_used.join(', ') : '';
    uses.innerHTML = `<span class="section-title">Uses:</span> ${escapeHTML(used)}`;

    const stepsEl = document.createElement('ol'); stepsEl.className = 'steps';
    steps.forEach(s => {
      const li = document.createElement('li');
      li.textContent = s;
      stepsEl.appendChild(li);
    });

    const stepsWrap = document.createElement('div');
    const stepsTitle = document.createElement('div'); stepsTitle.className = 'section-title'; stepsTitle.textContent = 'Cooking steps';
    stepsWrap.append(stepsTitle, stepsEl);

    body.append(uses, stepsWrap);
    card.appendChild(body);
    return card;
  }

  function makeBadge(text){ const b=document.createElement('span'); b.className='badge'; b.textContent=text; return b; }

  function prettifyPrep(line){
    return line.replace(/^prep\\s*time\\s*note\\s*:\\s*/i,'').trim();
  }

  function escapeHTML(s){ return (s||'').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

  document.getElementById('updateBtn').onclick = async () => {
    const payload = { items, updated_at: Date.now()/1000 };
    const r = await fetch('/api/update_pantry?merge=true', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const el = document.getElementById('status');
    if (r.ok) {
      const data = await r.json();
      items = data.items || items; // show merged pantry
      render();
      el.textContent = 'Saved & merged ✓';
    } else {
      el.textContent = 'Failed to save';
    }
    setTimeout(()=> el.textContent='', 2500);
  };

  document.getElementById('discardBtn').onclick = load;

  document.getElementById('voiceBtn').onclick = () => {
    const base = INGEST_BASE || (window.location.protocol + '//' + window.location.hostname + ':8000');
    window.location.href = base + '/';
  }

  load();
</script>
</body>
</html>
"""

@app.get("/review", response_class=HTMLResponse)
async def review_page():
    return HTMLResponse(REVIEW_HTML)
