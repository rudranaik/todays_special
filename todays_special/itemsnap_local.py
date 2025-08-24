import os, io, base64, time
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image

# LLM: OpenAI Responses API (vision + JSON schema)
import os
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv, dotenv_values

# 1) Resolve the .env path reliably (cwd or next to this file)
dotenv_path = find_dotenv(filename=".env", usecwd=True)
if not dotenv_path:
    dotenv_path = str((Path(__file__).parent / ".env").resolve())

# 2) Load and OVERRIDE existing env vars with values from .env
load_dotenv(dotenv_path, override=True)

MODEL_NAME = os.getenv("ITEMSNAP_MODEL", "gpt-5-nano-2025-08-07")  # fallback to gpt-4o-mini
print(f"""Using model: {os.getenv("ITEMSNAP_MODEL")} and API key: {os.getenv("OPENAI_API_KEY")}""")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Did you create a .env file?")

client = OpenAI(api_key=OPENAI_API_KEY)


# ==== APP ====
app = FastAPI(title="ItemSnap Local")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True
)

# ---- Shared JSON schema ----
class Item(BaseModel):
    name: str
    quantity: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None

class AnalysisResponse(BaseModel):
    items: list[Item]
    summary: str | None = None
    meta: dict | None = None

JSON_SCHEMA = {
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "quantity": {"type": "integer", "minimum": 0},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1},
          "notes": {"type": "string"}
        },
        "required": ["name", "quantity", "confidence"]
      }
    },
    "summary": {"type": "string"},
    "meta": {"type": "object"}
  },
  "required": ["items"]
}

SYSTEM_RULES = (
    "You are a meticulous inventory counter. "
    "Task: Identify distinct items in the image and count visible units.\n"
    "Rules:\n"
    "- Count physical units; if a sealed pack shows a printed count and units are not visible, use the printed count.\n"
    "- Prefer visible counts when both visible and printed are present.\n"
    "- Merge duplicates (one entry with total quantity).\n"
    "- Use generic names when brand is unclear.\n"
    "- Include confidence 0–1; add short notes if helpful.\n"
    "- Output only JSON that conforms to the provided schema."
)

def downscale_jpeg(file_bytes: bytes, max_side: int = 1600, quality: int = 80) -> bytes:
    im = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    w, h = im.size
    scale = max(w, h) / max_side if max(w, h) > max_side else 1.0
    if scale > 1.0:
        im = im.resize((int(w/scale), int(h/scale)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()

@app.get("/", response_class=HTMLResponse)
def index():
    # Simple inlined HTML+JS UI
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>ItemSnap Local</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }
  .card { max-width: 720px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 12px; }
  .row { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
  button { padding: 10px 14px; border: 0; border-radius: 10px; background: #2563eb; color: #fff; cursor: pointer; }
  button:disabled { opacity: 0.6; cursor: not-allowed; }
  pre { background: #0b1020; color: #e0e6ff; padding: 14px; border-radius: 12px; overflow: auto; }
  img { max-width: 100%; border-radius: 12px; margin-top: 10px; }
  .hint { color: #6b7280; font-size: 14px; }
</style>
</head>
<body>
  <div class="card">
    <h2>ItemSnap Local</h2>
    <p class="hint">Choose an image, then click “Analyze”. Runs locally; your API key stays on your machine.</p>
    <div class="row">
      <input id="file" type="file" accept="image/*" />
      <button id="analyze">Analyze</button>
      <span id="status" class="hint"></span>
    </div>
    <div id="preview"></div>
    <h3>JSON</h3>
    <pre id="out">{}</pre>
  </div>
<script>
const fileInput = document.getElementById('file');
const analyzeBtn = document.getElementById('analyze');
const out = document.getElementById('out');
const statusEl = document.getElementById('status');
const preview = document.getElementById('preview');

fileInput.addEventListener('change', () => {
  const f = fileInput.files?.[0];
  if (!f) return;
  const url = URL.createObjectURL(f);
  preview.innerHTML = '<img src="' + url + '" alt="preview" />';
  out.textContent = '{}';
});

analyzeBtn.addEventListener('click', async () => {
  const f = fileInput.files?.[0];
  if (!f) { alert('Pick an image first'); return; }
  try {
    statusEl.textContent = 'Uploading…';
    analyzeBtn.disabled = true;
    const form = new FormData();
    form.append('image', f, f.name || 'photo.jpg');
    const resp = await fetch('/analyze', { method: 'POST', body: form });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const json = await resp.json();
    out.textContent = JSON.stringify(json, null, 2);
    statusEl.textContent = 'Done';
  } catch (e) {
    out.textContent = JSON.stringify({ error: String(e) }, null, 2);
    statusEl.textContent = 'Error';
  } finally {
    analyzeBtn.disabled = false;
  }
});
</script>
</body>
</html>"""

@app.post("/analyze", response_model=AnalysisResponse)
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(image: UploadFile = File(...)):
    raw = await image.read()
    jpeg = downscale_jpeg(raw)  # resize for speed
    b64 = base64.b64encode(jpeg).decode("utf-8")
    b64_url = f"data:image/jpeg;base64,{b64}"

    t0 = time.time()

    chat = client.chat.completions.create(
        model=MODEL_NAME,  # e.g. "gpt-4o-mini"
        messages=[
            {
                "role": "system",
                "content": SYSTEM_RULES + "\nReturn ONLY valid JSON in the expected format."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Identify items and quantities in this image. "
                            "Produce JSON with: items[{name,quantity,confidence,notes?}], summary."
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": b64_url}
                    }
                ]
            }
        ],
        response_format={"type": "json_object"}  # ✅ ensures JSON output
    )

    # Extract the model's JSON string
    json_text = chat.choices[0].message.content

    # Validate & parse with Pydantic
    data = AnalysisResponse.model_validate_json(json_text)
    data.meta = {
        "source": "image",
        "duration_ms": int((time.time() - t0) * 1000),
        "model": MODEL_NAME
    }
    return JSONResponse(content=data.model_dump())
