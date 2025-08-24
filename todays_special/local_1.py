import os, io, base64, time, tempfile, re
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# OPTIONAL LLM/ASR: OpenAI SDK (kept for your extraction step; can be disabled)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from dotenv import load_dotenv, find_dotenv, dotenv_values

# NEW: faster-whisper (free, local)
from faster_whisper import WhisperModel

# 1) Resolve the .env path reliably (cwd or next to this file)
dotenv_path = find_dotenv(filename=".env", usecwd=True)
if not dotenv_path:
    dotenv_path = str((Path(__file__).parent / ".env").resolve())

# 2) Load and OVERRIDE existing env vars with values from .env
load_dotenv(dotenv_path, override=True)

# ===== Config =====
MODEL_NAME = os.getenv("ITEMSNAP_MODEL", "gpt-5-nano-2025-08-07")   # your extraction LLM (paid)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
USE_OPENAI_EXTRACTION = os.getenv("ITEMSNAP_USE_OPENAI", "1") == "1"  # set to "0" to use free local parser

# Faster‑Whisper knobs (all free/local)
FW_MODEL = os.getenv("ITEMSNAP_ASR_MODEL", "small")          # "tiny"|"base"|"small"|"medium"|"large-v3"
FW_COMPUTE = os.getenv("ITEMSNAP_ASR_COMPUTE", "int8")       # "int8" (fastest CPU), "float32", etc.
FW_BEAM = int(os.getenv("ITEMSNAP_ASR_BEAM", "5"))

print(f"Using extraction model: {MODEL_NAME} (OpenAI={'ON' if (USE_OPENAI_EXTRACTION and OPENAI_API_KEY) else 'OFF'})")
print(f"Using ASR (faster-whisper): model={FW_MODEL}, compute_type={FW_COMPUTE}, beam_size={FW_BEAM}")

# Create OpenAI client only if we’ll use it
client = None
if USE_OPENAI_EXTRACTION:
    if not OPENAI_API_KEY:
        print("[ItemSnap] OPENAI_API_KEY not found; falling back to local (free) extractor.")
        USE_OPENAI_EXTRACTION = False
    elif OpenAI is None:
        print("[ItemSnap] openai package not available; falling back to local (free) extractor.")
        USE_OPENAI_EXTRACTION = False
    else:
        client = OpenAI(api_key=OPENAI_API_KEY)

# ==== APP ====
app = FastAPI(title="ItemSnap Local (Audio)")
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
    "You are a meticulous inventory counter.\n"
    "Input: a transcript of a user speaking their pantry/grocery items (e.g., 'two cans chickpeas, a dozen eggs, 1 kg rice').\n"
    "Task: Identify distinct items and count units from the transcript.\n\n"
    "Rules:\n"
    "- Whichever language the user is speaking, you should return the items in English. You can mention the language for that item in the meta fields.\n"
    "- Count physical units; if quantities are verbal (e.g., 'two cans'), map to numeric units (quantity=2).\n"
    "- If both a package size and a unit count are present: quantity is the count of packages (e.g., 'three 400g cans' -> quantity=3), and you may note '400g' in notes.\n"
    "- Merge duplicates (single entry with total quantity).\n"
    "- Use generic names when brand is unclear.\n"
    "- If a quantity is implied as a single unit (e.g., 'a loaf of bread'), set quantity=1.\n"
    "- When quantity is unknown, set quantity=0 and explain briefly in notes.\n"
    "- Include confidence 0–1 for each item; add short notes if helpful.\n"
    "- Output only JSON that conforms to the provided schema (items[{name,quantity,confidence,notes?}], summary).\n"
)

# ---------- NEW: faster-whisper model (loaded once) ----------
# (Requires ffmpeg on PATH for webm/opus etc.)
fw_model = WhisperModel(FW_MODEL, compute_type=FW_COMPUTE)

# ---------------- UI ----------------
@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>ItemSnap Local (Record Audio)</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }
  .card { max-width: 760px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 12px; }
  .row { display: flex; gap: 12px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
  button { padding: 10px 14px; border: 0; border-radius: 10px; background: #2563eb; color: #fff; cursor: pointer; }
  button.secondary { background: #111827; }
  button:disabled { opacity: 0.6; cursor: not-allowed; }
  input[type="file"] { padding: 6px; }
  pre { background: #0b1020; color: #e0e6ff; padding: 14px; border-radius: 12px; overflow: auto; }
  audio { width: 100%; margin-top: 10px; }
  .hint { color: #6b7280; font-size: 14px; }
  .pill { font-variant-numeric: tabular-nums; background:#eef2ff; color:#3730a3; padding:2px 8px; border-radius:999px; }
</style>
</head>
<body>
  <div class="card">
    <h2>ItemSnap Local (Audio)</h2>
    <p class="hint">Click <strong>Record</strong>, speak your items (e.g., “two cans chickpeas, one dozen eggs, one kg rice”), then <strong>Stop</strong> and <strong>Analyze</strong>.</p>

    <div class="row">
      <button id="recBtn">🎙️ Record</button>
      <button id="stopBtn" disabled>■ Stop</button>
      <span id="timer" class="pill">00:00</span>
      <span id="status" class="hint"></span>
    </div>

    <div class="row">
      <input id="file" type="file" accept="audio/*" />
      <button id="useFile" class="secondary">Use File Instead</button>
    </div>

    <div id="preview"></div>

    <div class="row">
      <button id="analyze">Analyze</button>
    </div>

    <h3>JSON</h3>
    <pre id="out">{}</pre>
  </div>

<script>
let mediaRecorder, chunks = [], recordedBlob = null, timerInt = null, startedAt = 0;

const recBtn = document.getElementById('recBtn');
const stopBtn = document.getElementById('stopBtn');
const analyzeBtn = document.getElementById('analyze');
const useFileBtn = document.getElementById('useFile');
const fileInput = document.getElementById('file');

const out = document.getElementById('out');
const statusEl = document.getElementById('status');
const preview = document.getElementById('preview');
const timerEl = document.getElementById('timer');

function fmt(t){
  const s = Math.floor(t/1000);
  return String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0');
}
function startTimer(){
  startedAt = Date.now();
  timerInt = setInterval(()=>{ timerEl.textContent = fmt(Date.now()-startedAt); }, 200);
}
function stopTimer(){
  clearInterval(timerInt); timerInt=null;
}

recBtn.onclick = async () => {
  chunks = []; recordedBlob = null;
  out.textContent = '{}';
  statusEl.textContent = '';
  preview.innerHTML = '';

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus',
      audioBitsPerSecond: 48000
    });
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    mediaRecorder.onstop = () => {
      recordedBlob = new Blob(chunks, { type: 'audio/webm;codecs=opus' });
      const url = URL.createObjectURL(recordedBlob);
      const sizeKB = Math.round(recordedBlob.size / 1024);
      preview.innerHTML = '<audio controls src="' + url + '"></audio><div class="hint">Size: ' + sizeKB + ' KB</div>';
    };
    mediaRecorder.start();
    recBtn.disabled = true; stopBtn.disabled = false;
    startTimer();
  } catch (err) {
    statusEl.textContent = 'Mic error: ' + err;
  }
};

stopBtn.onclick = () => {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
  }
  recBtn.disabled = false; stopBtn.disabled = true;
  stopTimer();
};

useFileBtn.onclick = () => {
  fileInput.click();
};

fileInput.addEventListener('change', () => {
  const f = fileInput.files?.[0];
  if (!f) return;
  recordedBlob = f;
  const url = URL.createObjectURL(f);
  preview.innerHTML = '<audio controls src="' + url + '"></audio><div class="hint">File: ' + f.name + ' (' + Math.round(f.size/1024) + ' KB)</div>';
  out.textContent = '{}';
});

analyzeBtn.onclick = async () => {
  if (!recordedBlob) { alert('Record audio or choose a file first'); return; }
  try {
    statusEl.textContent = 'Uploading…';
    analyzeBtn.disabled = true;
    const form = new FormData();
    const fname = recordedBlob.name || 'speech.webm';
    form.append('audio', recordedBlob, fname);
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
};
</script>
</body>
</html>"""

# --------- Local (free) heuristic extractor as fallback ----------
_NUMBER_WORDS = {
    "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,
    "eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,
    "twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90,
    "hundred":100,"dozen":12,
    "a":1,"an":1
}
_UNITS = r"(cans?|packets?|packs?|bottles?|loaves?|eggs?|kg|kilograms?|g|grams?|l|liters?|ml|pieces?|pcs?)"

def _wordnum_to_int(tokens):
    # very small helper for phrases like "two", "one dozen", "twenty four"
    total = 0; current = 0
    for t in tokens:
        n = _NUMBER_WORDS.get(t)
        if n is None:
            continue
        if n == 100:
            current = max(1, current) * 100
        elif n == 12 and t == "dozen":
            current = max(1, current) * 12
        else:
            current += n
    total += current
    return total if total>0 else None

def _parse_items_free(text: str):
    txt = re.sub(r"[^a-zA-Z0-9\s\.-]", " ", text.lower())
    # Split by commas/and
    parts = re.split(r"[,\n;]+|\band\b", txt)
    bag = defaultdict(lambda: {"quantity":0, "notes":None})

    for p in parts:
        p = p.strip()
        if not p:
            continue

        # Try explicit numbers like "3 cans chickpeas" or "12 eggs"
        m = re.match(rf"(?:(\d+)|((?:\b[a-z]+\b\s?){1,3}))\s*(?:{_UNITS})?\s+([a-z][a-z0-9 \-]+)", p)
        qty = None; name = None; notes = None
        if m:
            if m.group(1):
                qty = int(m.group(1))
            else:
                qty = _wordnum_to_int(m.group(2).strip().split())
            name = m.group(3).strip()
        else:
            # Try unit-first like "two 400g cans of tomatoes" → qty from words, notes keep size
            m2 = re.match(rf"(?:(\d+)|((?:\b[a-z]+\b\s?){1,3}))\s*([0-9]+(?:g|kg|ml|l))?\s*(?:{_UNITS})?\s*(?:of)?\s*([a-z][a-z0-9 \-]+)", p)
            if m2:
                qty = int(m2.group(1)) if m2.group(1) else _wordnum_to_int((m2.group(2) or "").strip().split())
                if m2.group(3):
                    notes = m2.group(3)
                name = m2.group(4).strip()
            else:
                # Fallback: implied single, e.g., "rice", "a loaf of bread"
                m3 = re.match(rf"(?:a|an)?\s*(?:{_UNITS})?\s*(?:of)?\s*([a-z][a-z0-9 \-]+)", p)
                if m3:
                    qty = 1
                    name = m3.group(1).strip()

        if not name:
            continue

        # Normalize generic names a bit
        name = re.sub(r"\b(kg|g|ml|l|can|cans|pack|packs|packet|packets|bottle|bottles|loaf|loaves|pcs?|pieces?)\b", "", name).strip()
        name = re.sub(r"\s{2,}", " ", name)

        if qty is None:
            qty = 0

        # Merge duplicates
        bag[name]["quantity"] += qty
        if notes:
            bag[name]["notes"] = notes if not bag[name]["notes"] else f"{bag[name]['notes']}; {notes}"

    items = []
    for name, v in bag.items():
        items.append({
            "name": name,
            "quantity": int(v["quantity"]),
            "confidence": 0.6 if v["quantity"]>0 else 0.5,
            "notes": v["notes"]
        })
    return {
        "items": items,
        "summary": f"Parsed {len(items)} items from speech.",
    }

# -------------- Core endpoint: audio -> transcript -> JSON items --------------
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(audio: UploadFile = File(...)):
    t0 = time.time()

    # Validate content type roughly
    if not (audio.content_type or "").startswith("audio/"):
        # Some browsers may omit content-type; allow common extensions
        allowed_exts = (".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".webm")
        name = (audio.filename or "").lower()
        if not any(name.endswith(ext) for ext in allowed_exts):
            raise HTTPException(status_code=400, detail="Please upload an audio file")

    # Persist to temp file (faster-whisper expects a path; it will decode via ffmpeg)
    raw_bytes = await audio.read()
    suffix = Path(audio.filename or "speech.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        # 1) Transcribe (LOCAL, FREE)
        # NOTE: faster-whisper supports webm/opus, mp3, wav, etc., via ffmpeg
        segments, info = fw_model.transcribe(
            tmp_path,
            beam_size=FW_BEAM
        )
        transcript_text = " ".join(seg.text.strip() for seg in segments).strip()
        if not transcript_text:
            raise HTTPException(status_code=422, detail="Transcription returned empty text")

        # 2) Extract items JSON using your existing schema & rules
        if USE_OPENAI_EXTRACTION and client is not None:
            chat = client.chat.completions.create(
                model=MODEL_NAME,  # your extraction model (PAID)
                messages=[
                    {"role": "system", "content": SYSTEM_RULES + "\nReturn ONLY valid JSON in the expected format."},
                    {
                        "role": "user",
                        "content": (
                            "From the following transcript of spoken items, identify items and integer unit counts.\n"
                            "Produce JSON with: items[{name,quantity,confidence,notes?}], summary.\n\n"
                            f"Transcript:\n{transcript_text}"
                        )
                    },
                ],
                response_format={"type": "json_object"}
            )
            json_text = chat.choices[0].message.content
            data = AnalysisResponse.model_validate_json(json_text)
        else:
            # FREE fallback: quick deterministic parser
            parsed = _parse_items_free(transcript_text)
            data = AnalysisResponse.model_validate(parsed)

        # 3) Meta
        meta = {
            "source": "audio",
            "duration_ms": int((time.time() - t0) * 1000),
            "asr": {
                "engine": "faster-whisper",
                "model": FW_MODEL,
                "compute_type": FW_COMPUTE,
                "language": getattr(info, "language", None),
                "language_probability": getattr(info, "language_probability", None),
                "transcript_chars": len(transcript_text),
            },
            "extraction": "openai" if USE_OPENAI_EXTRACTION else "local-free",
            "llm_model": MODEL_NAME if USE_OPENAI_EXTRACTION else None
        }
        data.meta = {**(data.meta or {}), **meta}
        return JSONResponse(content=data.model_dump())

    finally:
        # Clean up temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass
