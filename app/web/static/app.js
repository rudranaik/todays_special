const apiBase = ""; // same-origin FastAPI app

const els = {
  pantryItems: document.getElementById("pantry-items"),
  refresh: document.getElementById("refresh"),
  save: document.getElementById("save"),
  addRow: document.getElementById("add-row"),
  mergeRows: document.getElementById("merge-rows"),
  name: document.getElementById("new-name"),
  qty: document.getElementById("new-qty"),
  unit: document.getElementById("new-unit"),
  toast: document.getElementById("toast"),
  suggestForm: document.getElementById("suggest-form"),
  suggestBtn: document.querySelector("#suggest-form button[type='submit']"),
  recipes: document.getElementById("recipes"),
  stagedItems: document.getElementById("staged-items"),
  pantryToggle: document.getElementById("pantry-toggle"),
  pantryContent: document.getElementById("pantry-content"),
  suggestStatus: document.getElementById("suggest-status"),
};

let localRows = []; // rows staged for merge

function renderStaged() {
  els.stagedItems.innerHTML = "";
  if (localRows.length === 0) {
    els.stagedItems.innerHTML = '<div class="muted">No items staged</div>';
  } else {
    localRows.forEach((r, i) => {
      const itemEl = document.createElement("div");
      itemEl.className = "pantry-item";
      itemEl.innerHTML = `
        <div class="pantry-item-details">
          <input class="name" data-i="${i}" data-k="name" value="${r.name}"/>
          <div class="quantity-unit">
            <input type="number" min="0" step="0.01" data-i="${i}" data-k="quantity" value="${r.quantity ?? 0}"/>
            <input data-i="${i}" data-k="unit" value="${r.unit ?? ""}"/>
          </div>
        </div>
        <button class="delete-btn" data-del="${i}">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-trash-2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
        </button>
      `;
      els.stagedItems.appendChild(itemEl);
    });
  }

  els.stagedItems.querySelectorAll("input").forEach(inp => {
    inp.addEventListener("change", () => {
      const i = Number(inp.dataset.i), k = inp.dataset.k;
      let v = inp.value;
      if (k === "quantity") v = Number(v);
      localRows[i][k] = v;
    });
  });

  els.stagedItems.querySelectorAll(".delete-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const i = Number(btn.dataset.del);
      localRows.splice(i, 1);
      renderStaged();
    });
  });

  els.mergeRows.disabled = localRows.length === 0;
}

function toast(msg, isError=false) {
  els.toast.textContent = msg;
  els.toast.classList.toggle("error", isError);
  els.toast.classList.add("show");
  setTimeout(() => { els.toast.classList.remove("show"); }, 5000);
}

function renderPantry(items) {
  els.pantryItems.innerHTML = "";
  items.forEach((it, idx) => {
    const itemEl = document.createElement("div");
    itemEl.className = "pantry-item";
    itemEl.innerHTML = `
      <div class="pantry-item-details">
        <input class="name" data-i="${idx}" data-k="name" value="${it.name}"/>
        <div class="quantity-unit">
          <input type="number" min="0" step="0.01" data-i="${idx}" data-k="quantity" value="${it.quantity ?? 0}"/>
          <input data-i="${idx}" data-k="unit" value="${it.unit ?? ""}"/>
        </div>
      </div>
      <button class="delete-btn" data-del="${idx}">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-trash-2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
      </button>
    `;
    els.pantryItems.appendChild(itemEl);
  });

  els.pantryItems.querySelectorAll("input").forEach(inp => {
    inp.addEventListener("change", () => {
      const i = Number(inp.dataset.i), k = inp.dataset.k;
      let v = inp.value;
      if (k === "quantity") v = Number(v);
      current.items[i][k] = v;
    });
  });

  els.pantryItems.querySelectorAll(".delete-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const i = Number(btn.dataset.del);
      current.items.splice(i, 1);
      renderPantry(current.items);
      await replacePantry();
    });
  });
}

let current = { items: [] };

async function loadPantry() {
  const r = await fetch(`${apiBase}/api/pantry`);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    toast(body.detail || "Failed to load pantry", true);
    return;
  }
  current = await r.json();
  renderPantry(current.items);
}

async function replacePantry() {
  const r = await fetch(`${apiBase}/api/pantry`, {
    method: "PUT",
    headers: { "Content-Type":"application/json" },
    body: JSON.stringify(current),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    toast(body.detail || "Save failed", true);
    return;
  }
  toast("Pantry saved");
  current = await r.json();
  renderPantry(current.items);
}

function rowFromInputs() {
  const name = els.name.value.trim();
  const qty = Number(els.qty.value || 0);
  const unit = els.unit.value.trim() || null;
  if (!name) { toast("Name required", true); return null; }
  if (qty < 0) { toast("Quantity must be ≥ 0", true); return null; }
  return { name, quantity: qty, unit };
}

function addLocalRow() {
  const row = rowFromInputs();
  if (!row) return;
  localRows.push(row);
  els.name.value = ""; els.qty.value = ""; els.unit.value = "";
  toast(`Staged: ${row.name} (${row.quantity || 0} ${row.unit || ""})`);
  renderStaged();
}

async function mergeRows() {
  if (localRows.length === 0) { toast("Nothing to merge"); return; }
  const rows = [...localRows]; // copy then reset
  localRows = [];
  const r = await fetch(`${apiBase}/api/pantry/merge`, {
    method: "POST",
    headers: { "Content-Type":"application/json" },
    body: JSON.stringify(rows),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    toast(body.detail || "Merge failed", true);
    return;
  }
  toast("Merged into pantry");
  await loadPantry();
  renderStaged();
}

async function suggestRecipes(ev) {
  ev.preventDefault();
  els.suggestBtn.disabled = true;
  const oldText = els.suggestBtn.textContent;
  els.suggestBtn.textContent = "Generating...";
  els.suggestStatus.textContent = "Generating recipes...";
  els.suggestStatus.hidden = false;
  const constraints = {
    time_minutes: els.time?.value ? Number(els.time.value) : null,
    mood: document.getElementById("mood").value || null,
    diet_conditions: (document.getElementById("diet").value || "").split(",").map(s => s.trim()).filter(Boolean),
    protein_goal_g: document.getElementById("protein").value ? Number(document.getElementById("protein").value) : null,
    servings: Number(document.getElementById("servings").value || 1),
  };
  const r = await fetch(`${apiBase}/api/suggest_recipes`, {
    method: "POST",
    headers: { "Content-Type":"application/json" },
    body: JSON.stringify(constraints),
  });
  const body = await r.json().catch(() => ({}));
  els.suggestBtn.disabled = false;
  els.suggestBtn.textContent = oldText;
  if (!r.ok) {
    toast(body.detail || "Suggest failed", true);
    els.suggestStatus.textContent = "Generation failed";
    setTimeout(() => (els.suggestStatus.hidden = true), 3000);
    return;
  }
  els.suggestStatus.textContent = "Recipes ready";
  setTimeout(() => (els.suggestStatus.hidden = true), 3000);
  renderRecipes(body.recipes || []);
}

function renderRecipes(recipes) {
  els.recipes.innerHTML = "";
  if (!recipes.length) {
    els.recipes.innerHTML = `<p class="muted">No recipes returned.</p>`;
    return;
  }
  recipes.forEach(r => {
    const div = document.createElement("div");
    div.className = "recipe";
    const tags = (r.tags || []).join(" • ");
    const steps = (r.steps || []).map(s => `<li>${s}</li>`).join("");
    const ing = (r.ingredients || []).map(i => `<li>${i.name} — ${i.quantity || 0} ${i.unit || ""}</li>`).join("");
    div.innerHTML = `
      <h3>${r.title}</h3>
      <div class="tags">${tags}</div>
      <details>
        <summary>Ingredients</summary>
        <ul>${ing}</ul>
      </details>
      <details>
        <summary>Steps</summary>
        <ol>${steps}</ol>
      </details>
      <div class="tags">~${r.est_time_minutes ?? "?"} min • ${r.est_kcal ?? "?"} kcal • ${r.est_protein_g ?? "?"} g protein</div>
    `;
    els.recipes.appendChild(div);
  });
}

// wire up
els.refresh.addEventListener("click", loadPantry);
els.save.addEventListener("click", replacePantry);
els.addRow.addEventListener("click", addLocalRow);
els.mergeRows.addEventListener("click", mergeRows);
els.suggestForm.addEventListener("submit", suggestRecipes);
els.pantryToggle.addEventListener("click", () => {
  const hidden = els.pantryContent.hidden;
  els.pantryContent.hidden = !hidden;
  els.pantryToggle.classList.toggle("collapsed", !hidden);
});

// expose time/servings ids
els.time = document.getElementById("time");

// initial load
loadPantry();
renderStaged();

// ---------------- Voice Ingest ----------------
let mediaRecorder = null;
let recordedChunks = [];
const vEls = {
  toggle: document.getElementById("rec-toggle"),
  audio: document.getElementById("rec-audio"),
  transcript: document.getElementById("rec-transcript"),
  extract: document.getElementById("rec-extract"),
  status: document.getElementById("transcribe-status"),
};

updateRecordButton(false);

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];

    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : (MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "");

    mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordedChunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
      const blob = new Blob(recordedChunks, { type: mime || "audio/webm" });
      vEls.audio.src = URL.createObjectURL(blob);
      vEls.audio.hidden = false;
      uploadAndTranscribe(blob);
    };

    mediaRecorder.start(100); // gather chunks every 100ms
    updateRecordButton(true);
    toast("Recording started");
  } catch (err) {
    toast(`Mic error: ${err.message || err}`, true);
  }
}

function stopRecording() {
  try {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach((t) => t.stop());
    }
    updateRecordButton(false);
  } catch (err) {
    toast(`Stop error: ${err.message || err}`, true);
  }
}

async function uploadAndTranscribe(blob) {
  try {
    vEls.status.textContent = "Transcribing...";
    vEls.status.hidden = false;
    const fd = new FormData();
    fd.append("file", blob, "note.webm");

    const r = await fetch(`${apiBase}/api/v1/ingest/transcribe`, {
      method: "POST",
      body: fd,
    });

    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      toast(body.detail || "Transcribe failed", true);
      vEls.status.textContent = "Transcription failed";
      setTimeout(() => (vEls.status.hidden = true), 3000);
      return;
    }

    vEls.transcript.value = body.transcript || "";
    vEls.status.textContent = "Transcription complete";
    setTimeout(() => (vEls.status.hidden = true), 3000);
    vEls.extract.disabled = false;

  } catch (err) {
    toast(`Upload error: ${err.message || err}`, true);
    vEls.status.textContent = "Transcription failed";
    setTimeout(() => (vEls.status.hidden = true), 3000);
  }
}

async function extractItemsFromTranscript() {
  const text = vEls.transcript.value.trim();
  if (!text) {
    toast("No transcript to extract from", true);
    return;
  }

  vEls.extract.disabled = true;
  vEls.status.textContent = "Extracting items...";
  vEls.status.hidden = false;

  const r = await fetch(`${apiBase}/api/v1/ingest/text`, {
    method: "POST",
    headers: { "Content-Type":"application/json" },
    body: JSON.stringify({ text }),
  });

  const body = await r.json().catch(() => ({}));
  vEls.extract.disabled = false;
  vEls.status.textContent = "Extraction complete";
  setTimeout(() => (vEls.status.hidden = true), 3000);

  if (!r.ok) {
    toast(body.detail || "Extraction failed", true);
    return;
  }

  const extracted = Array.isArray(body.items) ? body.items : [];

  if (extracted.length === 0) {
    toast("No items extracted from text.");
    return;
  }

  localRows.push(...extracted.map((i) => ({
    name: i.name,
    quantity: Number(i.quantity || 0),
    unit: i.unit || null,
  })));
  renderStaged();
  toast(`Staged ${extracted.length} items. Review in the staging area, then "Save Items to Pantry".`);
}

function updateRecordButton(rec) {
  if (rec) {
    vEls.toggle.textContent = "Stop & Transcribe";
    vEls.toggle.classList.add("recording");
  } else {
    vEls.toggle.textContent = "Start Recording";
    vEls.toggle.classList.remove("recording");
  }
}

function toggleRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    stopRecording();
  } else {
    startRecording();
  }
}

vEls.toggle?.addEventListener("click", toggleRecording);
vEls.extract?.addEventListener("click", extractItemsFromTranscript);
