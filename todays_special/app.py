import os, io, base64, time, tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# LLM/ASR: OpenAI SDK
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv, dotenv_values

# 1) Resolve the .env path reliably (cwd or next to this file)
dotenv_path = find_dotenv(filename=".env", usecwd=True)
if not dotenv_path:
    dotenv_path = str((Path(__file__).parent / ".env").resolve())

# 2) Load and OVERRIDE existing env vars with values from .env
load_dotenv(dotenv_path, override=True)

MODEL_NAME = os.getenv("ITEMSNAP_MODEL", "gpt-5-nano-2025-08-07")  # your original fallback/override
ASR_MODEL = os.getenv("ITEMSNAP_ASR_MODEL", "gpt-4o-mini-transcribe")           # speech-to-text model
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print(f"Using extraction model: {MODEL_NAME}")
print(f"Using ASR model: {ASR_MODEL}")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found. Did you create a .env file?")

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
    // Prefer opus/webm (small & fast to upload); tune bitrate for smaller files
    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus',
      audioBitsPerSecond: 48000  // ~48 kbps; adjust 24000–64000 for size/quality tradeoff
    });
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    mediaRecorder.onstop = () => {
      recordedBlob = new Blob(chunks, { type: 'audio/webm;codecs=opus' });
      const url = URL.createObjectURL(recordedBlob);
      const sizeKB = Math.round(recordedBlob.size / 1024);
      preview.innerHTML = '<audio controls src="' + url + '"></audio><div class="hint">Size: ' + sizeKB + ' KB</div>';
    };
    mediaRecorder.start(); // you can pass timeslice if you want periodic chunks
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

    # Persist to temp file (OpenAI SDK expects a real file handle for transcription)
    raw_bytes = await audio.read()
    suffix = Path(audio.filename or "speech.m4a").suffix or ".m4a"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        # 1) Transcribe
        with open(tmp_path, "rb") as f:
            asr = client.audio.transcriptions.create(
                model=ASR_MODEL,   # e.g., "whisper-1"
                file=f,
                # language="en",   # optionally force a language if your users are consistent
                # prompt="Grocery items and quantities may be mentioned.",  # optional bias
                response_format="json"
            )
        transcript_text = getattr(asr, "text", None) or ""
        if not transcript_text.strip():
            raise HTTPException(status_code=422, detail="Transcription returned empty text")

        # 2) Extract items JSON using your existing schema & rules
        chat = client.chat.completions.create(
            model=MODEL_NAME,  # your extraction model
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
            response_format={"type": "json_object"}  # ensure JSON output
        )

        json_text = chat.choices[0].message.content

        # 3) Validate & shape response
        data = AnalysisResponse.model_validate_json(json_text)
        data.meta = {
            "source": "audio",
            "duration_ms": int((time.time() - t0) * 1000),
            "model": MODEL_NAME,
            "asr_model": ASR_MODEL,
            "transcript_chars": len(transcript_text),
        }
        return JSONResponse(content=data.model_dump())

    finally:
        # Clean up temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass
