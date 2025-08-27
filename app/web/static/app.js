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

// ---- Identity & correlation helpers ----
function getDeviceId() {
  try {
    let id = localStorage.getItem('ts_device_id');
    if (!id) {
      id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : `dev-${Math.random().toString(36).slice(2)}-${Date.now()}`;
      localStorage.setItem('ts_device_id', id);
    }
    return id;
  } catch {
    return `dev-${Date.now()}`;
  }
}
function newCorrId() {
  try { return (crypto && crypto.randomUUID) ? crypto.randomUUID() : `corr-${Math.random().toString(36).slice(2)}-${Date.now()}`; }
  catch { return `corr-${Date.now()}`; }
}
const DEVICE_ID = getDeviceId();
let lastTranscribeCorrId = null;

let localRows = []; // rows staged for merge

// ---- Category grouping config ----
const CATEGORY_ORDER = [
  "Grains & Cereals",
  "Legumes & Pulses",
  "Vegetables - Leafy greens",
  "Vegetables - Root & tubers",
  "Vegetables - Cruciferous",
  "Vegetables - Others",
  "Fruits",
  "Herbs & Spices",
  "Oils & Fats",
  "Dairy & Alternatives",
  "Meat & Poultry",
  "Seafood",
  "Eggs",
  "Nuts & Seeds",
  "Condiments & Sauces",
  "Sweeteners",
  "Baking & Essentials",
  "Snacks & Miscellaneous",
  "Uncategorized",
];
const collapseState = new Map(); // category -> collapsed?
function isCollapsed(cat) { return collapseState.get(cat) === true; }
function toggleCollapsed(cat) { collapseState.set(cat, !isCollapsed(cat)); }

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

function renderPantryOld(items) {
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

// New grouped pantry renderer
function itemRowHTML(it, idx) {
  return `
    <div class="pantry-item">
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
    </div>
  `;
}

function renderPantry(items) {
  els.pantryItems.innerHTML = "";
  const pairs = items.map((it, idx) => ({ it, idx }));
  const groups = new Map();
  for (const p of pairs) {
    let cat = p.it.category || "Uncategorized";
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat).push(p);
  }
  const orderedCats = CATEGORY_ORDER.filter(c => groups.has(c));
  for (const cat of orderedCats) {
    const section = document.createElement('section');
    section.className = 'pantry-group';
    section.dataset.cat = cat;
    const collapsed = isCollapsed(cat);
    section.innerHTML = `
      <div class="pantry-group-header">
        <h3>${cat}</h3>
        <button class="icon-button group-toggle" aria-label="Toggle ${cat}" data-cat="${cat}">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"></polyline></svg>
        </button>
      </div>
      <div class="pantry-group-body" ${collapsed ? 'hidden' : ''}></div>
    `;
    const body = section.querySelector('.pantry-group-body');
    for (const {it, idx} of groups.get(cat)) {
      body.insertAdjacentHTML('beforeend', itemRowHTML(it, idx));
    }
    els.pantryItems.appendChild(section);
  }

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

  els.pantryItems.querySelectorAll('.group-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const cat = btn.dataset.cat;
      toggleCollapsed(cat);
      const sec = btn.closest('.pantry-group');
      const body = sec.querySelector('.pantry-group-body');
      const nowHidden = body.hasAttribute('hidden');
      if (nowHidden) body.removeAttribute('hidden'); else body.setAttribute('hidden','');
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
  const t0 = performance.now();
  const corr = newCorrId();
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
    headers: { "Content-Type":"application/json", "X-Device-Id": DEVICE_ID, "X-Correlation-Id": corr },
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
  // Post UI timing (click -> render finished)
  try {
    const dt = performance.now() - t0;
    await fetch(`${apiBase}/api/v1/metrics/ui`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "suggest_render", duration_ms: dt, user: DEVICE_ID, corr, extra: { count: (body.recipes || []).length } }),
    });
  } catch (_) { /* ignore */ }
}

function recipeToPlainText(r) {
  const ing = (r.ingredients || []).map(i => `- ${i.name}${(i.quantity || 0) ? ` — ${i.quantity} ${i.unit || ""}` : ""}`).join("\n");
  const prep = (r.preparation || []).map((s, i) => `${i + 1}. ${s}`).join("\n");
  const steps = (r.steps || []).map((s, i) => `${i + 1}. ${s}`).join("\n");
  const tags = (r.tags || []).join(", ");
  const meta = `~${r.est_prep_time_minutes ?? "?"} min prep • ~${r.est_time_minutes ?? "?"} min cook • ${r.est_kcal ?? "?"} kcal • ${r.est_protein_g ?? "?"} g protein`;
  return `${r.title}\n${tags ? `Tags: ${tags}\n` : ""}${meta}\n\nIngredients:\n${ing}\n\nPreparation:\n${prep}\n\nSteps:\n${steps}`;
}

async function saveFavorite(recipe, btnEl) {
  try {
    const resp = await fetch(`${apiBase}/api/v1/favorites`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Device-Id": DEVICE_ID },
      body: JSON.stringify(recipe),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || "Save to favorites failed");
    }
    toast("Saved to favorites");
    if (btnEl) {
      btnEl.textContent = "Saved to favorites";
      btnEl.disabled = true;
      btnEl.classList.remove("primary");
    }
  } catch (e) {
    toast(e.message || String(e), true);
  }
}

async function copyRecipe(recipe) {
  try {
    await navigator.clipboard.writeText(recipeToPlainText(recipe));
    toast("Recipe copied to clipboard");
  } catch (e) {
    toast("Copy failed", true);
  }
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
    const prep = (r.preparation || []).map(s => `<li>${s}</li>`).join("");
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
        <summary>Preparation</summary>
        <ol>${prep}</ol>
      </details>
      <details>
        <summary>Steps</summary>
        <ol>${steps}</ol>
      </details>
      <div class="tags">~${r.est_prep_time_minutes ?? "?"} min prep • ~${r.est_time_minutes ?? "?"} min cook • ${r.est_kcal ?? "?"} kcal • ${r.est_protein_g ?? "?"} g protein</div>
      <div class="row">
        <button class="copy-btn">Copy recipe</button>
        <button class="fav-btn primary">Save to Favorites</button>
      </div>
    `;
    els.recipes.appendChild(div);

    // Wire buttons
    div.querySelector(".copy-btn")?.addEventListener("click", () => copyRecipe(r));
    const favBtn = div.querySelector(".fav-btn");
    favBtn?.addEventListener("click", () => saveFavorite(r, favBtn));
  });
}

// wire up
els.refresh?.addEventListener("click", loadPantry);
els.save?.addEventListener("click", replacePantry);
els.addRow?.addEventListener("click", addLocalRow);
els.mergeRows?.addEventListener("click", mergeRows);
els.suggestForm?.addEventListener("submit", suggestRecipes);
els.pantryToggle?.addEventListener("click", () => {
  const hidden = els.pantryContent.hidden;
  els.pantryContent.hidden = !hidden;
  els.pantryToggle.classList.toggle("collapsed", !hidden);
});

// expose time/servings ids
els.time = document.getElementById("time");

// initial load for pantry page
if (els.pantryItems) {
  loadPantry();
  renderStaged();
}

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

if (vEls.toggle) updateRecordButton(false);

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
    const t0 = performance.now();
    const corr = newCorrId();
    lastTranscribeCorrId = corr;
    vEls.status.textContent = "Transcribing...";
    vEls.status.hidden = false;
    const fd = new FormData();
    fd.append("file", blob, "note.webm");

    const r = await fetch(`${apiBase}/api/v1/ingest/transcribe`, {
      method: "POST",
      headers: { "X-Device-Id": DEVICE_ID, "X-Correlation-Id": corr },
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

    // Post UI timing (upload start -> transcript ready)
    try {
      const dt = performance.now() - t0;
      await fetch(`${apiBase}/api/v1/metrics/ui`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "transcribe_e2e", duration_ms: dt, user: DEVICE_ID, corr, extra: { size_bytes: blob.size } }),
      });
    } catch (_) { /* ignore */ }

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

  const t0 = performance.now();
  const corr = lastTranscribeCorrId || newCorrId();
  vEls.extract.disabled = true;
  vEls.status.textContent = "Extracting items...";
  vEls.status.hidden = false;

  const r = await fetch(`${apiBase}/api/v1/ingest/text`, {
    method: "POST",
    headers: { "Content-Type":"application/json", "X-Device-Id": DEVICE_ID, "X-Correlation-Id": corr },
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
    category: i.category || null,
  })));
  renderStaged();
  toast(`Staged ${extracted.length} items. Review in the staging area, then "Save Items to Pantry".`);

  // Post UI timing (click -> staged items rendered)
  try {
    const dt = performance.now() - t0;
    await fetch(`${apiBase}/api/v1/metrics/ui`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "extract_items_e2e", duration_ms: dt, user: DEVICE_ID, corr, extra: { count: extracted.length } }),
    });
  } catch (_) { /* ignore */ }
}

function updateRecordButton(rec) {
  if (!vEls.toggle) return;
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

// --------------- Favorites page ---------------
const favListEl = document.getElementById("favorites");

async function removeFavorite(id) {
  try {
    const resp = await fetch(`${apiBase}/api/v1/favorites/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: { "X-Device-Id": DEVICE_ID },
    });
    if (!resp.ok) {
      const b = await resp.json().catch(() => ({}));
      throw new Error(b.detail || "Remove failed");
    }
    await loadFavorites();
  } catch (e) {
    toast(e.message || String(e), true);
  }
}

function renderFavorites(recipes) {
  if (!favListEl) return;
  favListEl.innerHTML = "";
  if (!recipes.length) {
    favListEl.innerHTML = `<p class="muted">No favorites yet. Save recipes you like to see them here.</p>`;
    return;
  }
  recipes.forEach(r => {
    const div = document.createElement("div");
    div.className = "recipe";
    const tags = (r.tags || []).join(" • ");
    const prep = (r.preparation || []).map(s => `<li>${s}</li>`).join("");
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
        <summary>Preparation</summary>
        <ol>${prep}</ol>
      </details>
      <details>
        <summary>Steps</summary>
        <ol>${steps}</ol>
      </details>
      <div class="tags">~${r.est_prep_time_minutes ?? "?"} min prep • ~${r.est_time_minutes ?? "?"} min cook • ${r.est_kcal ?? "?"} kcal • ${r.est_protein_g ?? "?"} g protein</div>
      <div class="row">
        <button class="copy-btn">Copy recipe</button>
        <button class="remove-fav-btn">Remove</button>
      </div>
    `;
    favListEl.appendChild(div);
    div.querySelector(".copy-btn")?.addEventListener("click", () => copyRecipe(r));
    div.querySelector(".remove-fav-btn")?.addEventListener("click", () => removeFavorite(r.id));
  });
}

async function loadFavorites() {
  if (!favListEl) return;
  try {
    const resp = await fetch(`${apiBase}/api/v1/favorites`, { headers: { "X-Device-Id": DEVICE_ID } });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.detail || "Failed to load favorites");
    renderFavorites(body.recipes || []);
  } catch (e) {
    renderFavorites([]);
    toast(e.message || String(e), true);
  }
}

if (favListEl) {
  loadFavorites();
}
