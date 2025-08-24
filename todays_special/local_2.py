# local_stream.py
# FastAPI app with:
#  - Web UI (/)
#  - WebSocket streaming partial transcription (/ws/transcribe)
#  - File upload -> full transcription + JSON extraction (/analyze)
#
# ASR: faster-whisper (free, local)
# Optional extraction: OpenAI LLM (set ITEMSNAP_USE_OPENAI=1 and OPENAI_API_KEY)
#
# deps:
#   pip install fastapi uvicorn python-multipart pydantic dotenv faster-whisper
# plus ffmpeg in PATH (e.g., brew install ffmpeg)

import os, time, tempfile, re
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv, find_dotenv

# Optional OpenAI (for JSON extraction step). App works fine without it.
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ---- Load env ----
dotenv_path = find_dotenv(filename=".env", usecwd=True) or str((Path(__file__).parent / ".env").resolve())
load_dotenv(dotenv_path, override=True)

MODEL_NAME = os.getenv("ITEMSNAP_MODEL", "gpt-5-nano")      # extraction LLM (optional)
USE_OPENAI_EXTRACTION = os.getenv("ITEMSNAP_USE_OPENAI", "0") == "1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---- faster-whisper config ----
FW_MODEL_RAW = os.getenv("ITEMSNAP_ASR_MODEL", "small")     # tiny|base|small|medium|large-v3|...
FW_COMPUTE   = os.getenv("ITEMSNAP_ASR_COMPUTE", "int8")    # int8 (fast CPU), float16, float32
FW_BEAM      = int(os.getenv("ITEMSNAP_ASR_BEAM", "1"))     # 1 for snappy streaming; raise for accuracy

def _normalize_fw_model(name: str) -> str:
    name = (name or "").strip()
    mapping = {
        "whisper-1": "small",
        "gpt-4o-mini-transcribe": "small",
        "gpt-4o-transcribe": "medium",
    }
    valid = {
        "tiny","tiny.en","base","base.en","small","small.en",
        "medium","medium.en","large-v1","large-v2","large-v3","large",
        "distil-large-v2","distil-medium.en","distil-small.en",
        "distil-large-v3","distil-large-v3.5","large-v3-turbo","turbo"
    }
    return mapping.get(name, name if name in valid else "small")

FW_MODEL = _normalize_fw_model(FW_MODEL_RAW)

# ---- Initialize faster-whisper ----
from faster_whisper import WhisperModel
try:
    fw_model = WhisperModel(FW_MODEL, compute_type=FW_COMPUTE)
except ValueError as e:
    print(f"[ItemSnap] Bad ASR model '{FW_MODEL}', falling back to 'small' ({e})")
    FW_MODEL = "small"
    fw_model = WhisperModel(FW_MODEL, compute_type=FW_COMPUTE)

# ---- Optional OpenAI client ----
client = None
if USE_OPENAI_EXTRACTION and OPENAI_API_KEY and OpenAI is not None:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    if USE_OPENAI_EXTRACTION:
        print("[ItemSnap] OpenAI extraction requested but key/pkg missing; using local parser.")
    USE_OPENAI_EXTRACTION = False

print(f"Using extraction model: {MODEL_NAME} (OpenAI={'ON' if USE_OPENAI_EXTRACTION else 'OFF'})")
print(f"Using ASR (faster-whisper): model={FW_MODEL}, compute_type={FW_COMPUTE}, beam_size={FW_BEAM}")

# ---- FastAPI app ----
app = FastAPI(title="ItemSnap Streaming (Audio)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True
)

# ---- Schema models ----
class Item(BaseModel):
    name: str
    quantity: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None

class AnalysisResponse(BaseModel):
    items: list[Item]
    summary: str | None = None
    meta: dict | None = None

SYSTEM_RULES = (
    "You are a meticulous inventory counter.\n"
    "Input: a transcript of a user speaking their pantry/grocery items (e.g., 'two cans chickpeas, a dozen eggs, 1 kg rice').\n"
    "Task: Identify distinct items and count units from the transcript.\n\n"
    "Rules:\n"
    "- Return items in English; note language in notes if helpful.\n"
    "- Count packages as units (e.g., 'three 400g cans' -> quantity=3; note '400g').\n"
    "- Merge duplicates; generic names if brand unclear.\n"
    "- If implied single, set quantity=1; if unknown, set 0 and explain briefly.\n"
    "- Include confidence 0–1; keep notes short.\n"
    "- Output ONLY valid JSON with items[{name,quantity,confidence,notes?}], summary.\n"
)

# ---- Simple free parser (fallback if no OpenAI) ----
_NUMBER_WORDS = {
    "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,
    "eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,
    "twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90,
    "hundred":100,"dozen":12, "a":1,"an":1
}
_UNITS = r"(cans?|packets?|packs?|bottles?|loaves?|eggs?|kg|kilograms?|g|grams?|l|liters?|ml|pieces?|pcs?)"

def _wordnum_to_int(tokens):
    total = 0; current = 0
    for t in tokens:
        n = _NUMBER_WORDS.get(t)
        if n is None: continue
        if n == 100: current = max(1, current) * 100
        elif n == 12 and t == "dozen": current = max(1, current) * 12
        else: current += n
    total += current
    return total if total>0 else None

def parse_items_free(text: str):
    txt = re.sub(r"[^a-zA-Z0-9\s\.-]", " ", text.lower())
    parts = re.split(r"[,\n;]+|\band\b", txt)
    bag = defaultdict(lambda: {"quantity":0, "notes":None})

    for p in parts:
        p = p.strip()
        if not p: continue
        qty = None; name = None; notes = None

        m = re.match(rf"(?:(\d+)|((?:\b[a-z]+\b\s?){1,3}))\s*(?:{_UNITS})?\s+([a-z][a-z0-9 \-]+)", p)
        if m:
            qty = int(m.group(1)) if m.group(1) else _wordnum_to_int(m.group(2).strip().split())
            name = m.group(3).strip()
        else:
            m2 = re.match(rf"(?:(\d+)|((?:\b[a-z]+\b\s?){1,3}))\s*([0-9]+(?:g|kg|ml|l))?\s*(?:{_UNITS})?\s*(?:of)?\s*([a-z][a-z0-9 \-]+)", p)
            if m2:
                qty = int(m2.group(1)) if m2.group(1) else _wordnum_to_int((m2.group(2) or "").strip().split())
                if m2.group(3): notes = m2.group(3)
                name = m2.group(4).strip()
            else:
                m3 = re.match(rf"(?:a|an)?\s*(?:{_UNITS})?\s*(?:of)?\s*([a-z][a-z0-9 \-]+)", p)
                if m3:
                    qty = 1; name = m3.group(1).strip()

        if not name: continue
        name = re.sub(r"\b(kg|g|ml|l|can|cans|pack|packs|packet|packets|bottle|bottles|loaf|loaves|pcs?|pieces?)\b", "", name).strip()
        name = re.sub(r"\s{2,}", " ", name)
        qty = qty if qty is not None else 0

        bag[name]["quantity"] += qty
        if notes:
            bag[name]["notes"] = notes if not bag[name]["notes"] else f"{bag[name]['notes']}; {notes}"

    items = [{"name": k, "quantity": int(v["quantity"]), "confidence": 0.6 if v["quantity"]>0 else 0.5, "notes": v["notes"]} for k,v in bag.items()]
    return {"items": items, "summary": f"Parsed {len(items)} items from speech."}

# ---- Helpers ----
def fw_transcribe_text(path: str, fast=True) -> str:
    # Latency-lean settings for streaming/partials; adjust for accuracy later
    kwargs = dict(
        vad_filter=True,
        # chunk_size=5 if fast else 15,
        beam_size=1 if fast else FW_BEAM,
        temperature=0.0,
        no_speech_threshold=0.6,
    )
    segments, info = fw_model.transcribe(path, **kwargs)
    return " ".join(s.text.strip() for s in segments).strip()

# ---- UI ----
@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>ItemSnap Streaming (Audio)</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }
  .card { max-width: 820px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 12px; }
  .row { display: flex; gap: 12px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
  button { padding: 10px 14px; border: 0; border-radius: 10px; background: #2563eb; color: #fff; cursor: pointer; }
  button.secondary { background: #111827; }
  button:disabled { opacity: 0.6; cursor: not-allowed; }
  input[type="file"] { padding: 6px; }
  pre { background: #0b1020; color: #e0e6ff; padding: 14px; border-radius: 12px; overflow: auto; min-height: 80px; }
  audio { width: 100%; margin-top: 10px; }
  .hint { color: #6b7280; font-size: 14px; }
  .pill { font-variant-numeric: tabular-nums; background:#eef2ff; color:#3730a3; padding:2px 8px; border-radius:999px; }
</style>
</head>
<body>
  <div class="card">
    <h2>ItemSnap Streaming (Audio)</h2>
    <p class="hint">Record and watch the <strong>Live Transcript</strong> appear as you speak. Or upload a file and click <strong>Analyze</strong>.</p>

    <div class="row">
      <button id="recBtn">🎙️ Record (stream)</button>
      <button id="stopBtn" disabled>■ Stop</button>
      <span id="timer" class="pill">00:00</span>
      <span id="status" class="hint"></span>
    </div>

    <h3>Live Transcript</h3>
    <pre id="live"></pre>

    <div class="row">
      <input id="file" type="file" accept="audio/*" />
      <button id="useFile" class="secondary">Use File Instead</button>
      <button id="analyze">Analyze</button>
    </div>

    <div id="preview"></div>

    <h3>Extracted JSON</h3>
    <pre id="out">{}</pre>
  </div>

<script>
let mediaRecorder, recordedBlob = null, timerInt = null, startedAt = 0, ws = null, chunks = [];
const recBtn = document.getElementById('recBtn');
const stopBtn = document.getElementById('stopBtn');
const analyzeBtn = document.getElementById('analyze');
const useFileBtn = document.getElementById('useFile');
const fileInput = document.getElementById('file');
const out = document.getElementById('out');
const statusEl = document.getElementById('status');
const preview = document.getElementById('preview');
const timerEl = document.getElementById('timer');
const live = document.getElementById('live');

function fmt(t){ const s = Math.floor(t/1000); return String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0'); }
function startTimer(){ startedAt = Date.now(); timerInt = setInterval(()=>{ timerEl.textContent = fmt(Date.now()-startedAt); }, 200); }
function stopTimer(){ clearInterval(timerInt); timerInt=null; }

async function startStreaming() {
  ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/transcribe');
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.error) { live.textContent = '[error] ' + msg.error; return; }
      live.textContent = (msg.final ? '[final] ' : '[partial] ') + (msg.text || '');
      if (msg.final) { // auto-run analysis on final?
        // Optionally copy to out or call /analyze with a file; we keep UX simple here.
      }
    } catch (e) { console.warn('WS parse error', e); }
  };
}

recBtn.onclick = async () => {
  chunks = []; recordedBlob = null; out.textContent = '{}'; statusEl.textContent = ''; preview.innerHTML = ''; live.textContent = '';
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    await startStreaming();
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 48000 });
    mediaRecorder.ondataavailable = async (e) => {
      if (e.data && e.data.size > 0) {
        chunks.push(e.data);
        if (ws && ws.readyState === WebSocket.OPEN) {
          const buf = await e.data.arrayBuffer();
          ws.send(buf);
        }
      }
    };
    mediaRecorder.start(250); // 250ms slices
    recBtn.disabled = true; stopBtn.disabled = false; startTimer();
  } catch (err) {
    statusEl.textContent = 'Mic/WS error: ' + err;
  }
};

stopBtn.onclick = async () => {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('__STOP__');
  }
  // Build a Blob from chunks for optional /analyze
  if (chunks.length) {
    recordedBlob = new Blob(chunks, { type: 'audio/webm;codecs=opus' });
    const url = URL.createObjectURL(recordedBlob);
    const sizeKB = Math.round(recordedBlob.size / 1024);
    preview.innerHTML = '<audio controls src="' + url + '"></audio><div class="hint">Size: ' + sizeKB + ' KB</div>';
  }
  recBtn.disabled = false; stopBtn.disabled = true; stopTimer();
};

useFileBtn.onclick = () => fileInput.click();
fileInput.addEventListener('change', () => {
  const f = fileInput.files?.[0]; if (!f) return;
  recordedBlob = f;
  const url = URL.createObjectURL(f);
  preview.innerHTML = '<audio controls src="' + url + '"></audio><div class="hint">File: ' + f.name + ' (' + Math.round(f.size/1024) + ' KB)</div>';
  out.textContent = '{}';
});

analyzeBtn.onclick = async () => {
  if (!recordedBlob) { alert('Record or choose a file first'); return; }
  try {
    statusEl.textContent = 'Uploading…'; analyzeBtn.disabled = true;
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

# ---- WebSocket: streaming partials ----
@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket):
    await ws.accept()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    tmp_path = tmp.name
    tmp.close()

    bytes_since_last = 0
    # With audioBitsPerSecond ~48kbps in the UI, ~32–64 KB ~= 2–4s audio (tune as you like)
    MIN_STEP_BYTES = 32_000

    try:
        while True:
            msg = await ws.receive()
            if "bytes" in msg:
                with open(tmp_path, "ab") as f:
                    f.write(msg["bytes"])
                bytes_since_last += len(msg["bytes"])

                if bytes_since_last >= MIN_STEP_BYTES:
                    try:
                        partial_text = fw_transcribe_text(tmp_path, fast=True)
                        await ws.send_json({"final": False, "text": partial_text})
                    except Exception as e:
                        await ws.send_json({"final": False, "error": str(e)})
                    bytes_since_last = 0

            elif "text" in msg:
                if msg["text"] == "__STOP__":
                    final_text = fw_transcribe_text(tmp_path, fast=False)
                    await ws.send_json({"final": True, "text": final_text})
                    break

    except WebSocketDisconnect:
        pass
    finally:
        try: os.remove(tmp_path)
        except Exception: pass
        try: await ws.close()
        except Exception: pass

# ---- Full analyze: upload -> transcript -> (optional) JSON extraction ----
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(audio: UploadFile = File(...)):
    t0 = time.time()

    if not (audio.content_type or "").startswith("audio/"):
        allowed_exts = (".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".webm")
        name = (audio.filename or "").lower()
        if not any(name.endswith(ext) for ext in allowed_exts):
            raise HTTPException(status_code=400, detail="Please upload an audio file")

    raw_bytes = await audio.read()
    suffix = Path(audio.filename or "speech.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        # Full-pass (slightly slower but better quality) transcription
        segments, info = fw_model.transcribe(
            tmp_path,
            vad_filter=True,
            # chunk_size=15,
            beam_size=max(1, FW_BEAM),
            temperature=0.0
        )
        transcript_text = " ".join(s.text.strip() for s in segments).strip()
        if not transcript_text:
            raise HTTPException(status_code=422, detail="Transcription returned empty text")

        # Extraction: OpenAI (optional) or local free parser
        if USE_OPENAI_EXTRACTION and client is not None:
            chat = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_RULES + "\nReturn ONLY valid JSON in the expected format."},
                    {"role": "user", "content": f"Transcript:\n{transcript_text}"}
                ],
                response_format={"type": "json_object"}
            )
            json_text = chat.choices[0].message.content
            # minimal validation: return directly (or use pydantic model_parse_json)
            from json import loads
            data = loads(json_text)
        else:
            data = parse_items_free(transcript_text)

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
        # Return merged payload
        return JSONResponse(content={**data, "meta": meta})

    finally:
        try: os.remove(tmp_path)
        except Exception: pass
