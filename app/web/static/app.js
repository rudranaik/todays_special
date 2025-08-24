const apiBase = ""; // same-origin FastAPI app

const els = {
  tbody: document.getElementById("pantry-body"),
  refresh: document.getElementById("refresh"),
  save: document.getElementById("save"),
  addRow: document.getElementById("add-row"),
  mergeRows: document.getElementById("merge-rows"),
  name: document.getElementById("new-name"),
  qty: document.getElementById("new-qty"),
  unit: document.getElementById("new-unit"),
  toast: document.getElementById("toast"),
  suggestForm: document.getElementById("suggest-form"),
  recipes: document.getElementById("recipes"),
};

let localRows = []; // rows staged for merge

function toast(msg, isError=false) {
  els.toast.textContent = msg;
  els.toast.hidden = false;
  els.toast.classList.toggle("error", isError);
  setTimeout(() => { els.toast.hidden = true; }, 3500);
}

function renderPantry(items) {
  els.tbody.innerHTML = "";
  items.forEach((it, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input data-i="${idx}" data-k="name" value="${it.name}"/></td>
      <td><input type="number" min="0" step="0.01" data-i="${idx}" data-k="quantity" value="${it.quantity ?? 0}"/></td>
      <td><input data-i="${idx}" data-k="unit" value="${it.unit ?? ""}"/></td>
      <td><button class="danger" data-del="${idx}">Delete</button></td>`;
    els.tbody.appendChild(tr);
  });

  els.tbody.querySelectorAll("input").forEach(inp => {
    inp.addEventListener("change", () => {
      const i = Number(inp.dataset.i), k = inp.dataset.k;
      let v = inp.value;
      if (k === "quantity") v = Number(v);
      current.items[i][k] = v;
    });
  });

  els.tbody.querySelectorAll("button[data-del]").forEach(btn => {
    btn.addEventListener("click", () => {
      const i = Number(btn.dataset.del);
      current.items.splice(i, 1);
      renderPantry(current.items);
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
  current = body;
  renderPantry(current.items);
  toast("Merged into pantry");
}

async function suggestRecipes(ev) {
  ev.preventDefault();
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
  if (!r.ok) {
    toast(body.detail || "Suggest failed", true);
    return;
  }
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

// expose time/servings ids
els.time = document.getElementById("time");

// initial load
loadPantry();

// ---------------- Voice Ingest ----------------
let mediaRecorder = null;
let recordedChunks = [];
const vEls = {
  start: document.getElementById("rec-start"),
  stop: document.getElementById("rec-stop"),
  lang: document.getElementById("rec-lang"),
  audio: document.getElementById("rec-audio"),
  transcript: document.getElementById("rec-transcript"),
  merge: document.getElementById("rec-merge"),
};

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
      uploadAndExtract(blob);
    };

    mediaRecorder.start(100); // gather chunks every 100ms
    vEls.start.disabled = true;
    vEls.stop.disabled = false;
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
    vEls.start.disabled = false;
    vEls.stop.disabled = true;
  } catch (err) {
    toast(`Stop error: ${err.message || err}`, true);
  }
}

async function uploadAndExtract(blob) {
  try {
    const fd = new FormData();
    fd.append("file", blob, "note.webm");
    const lang = (vEls.lang.value || "").trim();
    if (lang) fd.append("language", lang);

    const r = await fetch(`${apiBase}/api/voice/transcribe_extract`, {
      method: "POST",
      body: fd,
    });

    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      toast(body.detail || "Transcribe/Extract failed", true);
      return;
    }

    vEls.transcript.value = body.transcript || "";
    const extracted = Array.isArray(body.items) ? body.items : [];

    if (extracted.length === 0) {
      toast("No items extracted from voice.");
      vEls.merge.disabled = true;
      return;
    }

    // stage into localRows for review, not directly into pantry
    localRows.push(...extracted.map((i) => ({
      name: i.name,
      quantity: Number(i.quantity || 0),
      unit: i.unit || null,
    })));

    // show a toast and enable Merge button
    toast(`Staged ${extracted.length} items from voice. Review below, then "Merge Into Pantry".`);
    vEls.merge.disabled = false;
  } catch (err) {
    toast(`Upload error: ${err.message || err}`, true);
  }
}

vEls.start?.addEventListener("click", startRecording);
vEls.stop?.addEventListener("click", stopRecording);
vEls.merge?.addEventListener("click", async () => {
  // Reuse existing mergeRows (it consumes localRows and merges into pantry)
  await mergeRows();
  vEls.merge.disabled = true;
});
