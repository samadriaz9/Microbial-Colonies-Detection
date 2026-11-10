const state = { user: null, config: {}, poll: null, previews: [] };
const app = document.getElementById("app");

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function current() {
  const raw = (location.hash || "#/dashboard").replace(/^#/, "");
  const [path, query] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  return { name: parts[0] || "dashboard", id: parts[1] || "", query: new URLSearchParams(query || "") };
}

function stopPoll() {
  if (state.poll) clearInterval(state.poll);
  state.poll = null;
}

function clearPreviews() {
  state.previews.forEach((url) => URL.revokeObjectURL(url));
  state.previews = [];
}

function toast(message) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3200);
}

function when(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function num(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toLocaleString();
}

function duration(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

async function api(path, options = {}) {
  const opts = { ...options };
  const headers = new Headers(opts.headers || {});
  if (Object.prototype.hasOwnProperty.call(opts, "json")) {
    headers.set("content-type", "application/json");
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  delete opts.headers;
  const run = () => fetch(path, { credentials: "include", ...opts, headers });
  let response = await run();
  if (
    response.status === 401
    && path !== "/api/auth/login"
    && path !== "/api/auth/register"
    && path !== "/api/auth/google"
    && path !== "/api/auth/refresh"
  ) {
    const refreshed = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
    if (refreshed.ok) response = await run();
    else state.user = null;
  }
  return response;
}

async function readError(response) {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg || "Invalid value").join(" ");
  } catch (_err) {
    /* response had no JSON body */
  }
  return "The request failed.";
}

function icon(name) {
  const paths = {
    dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    history: '<path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 4v5h5"/><path d="M12 8v5l3 2"/>',
    logout: '<path d="M9 6H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/><path d="M14 16l4-4-4-4"/><path d="M18 12H9"/>',
    search: '<circle cx="11" cy="11" r="6"/><path d="M16 16l4 4"/>',
    trash: '<path d="M4 7h16"/><path d="M9 7V5h6v2"/><path d="M7 7l1 12h8l1-12"/>',
    download: '<path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/>',
    image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="M21 16l-5-5-9 8"/>',
    grid: '<rect x="3" y="3" width="7" height="5" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="3" y="11" width="7" height="5" rx="1"/><rect x="14" y="11" width="7" height="5" rx="1"/><rect x="3" y="19" width="18" height="2" rx="1"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    plate: '<circle cx="12" cy="12" r="8"/><circle cx="9" cy="10" r="1"/><circle cx="14" cy="13" r="1.4"/>',
  };
  return `<span class="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name] || ""}</svg></span>`;
}

function brand() {
  return `<img class="logo" src="/logo.png" alt="" width="40" height="40" /><span><strong>Colonies</strong><small>Detection</small></span>`;
}

function layout(content) {
  const route = current().name;
  const initial = (state.user.name || "?").trim().charAt(0).toUpperCase();
  return `
    <div class="shell">
      <aside class="sidebar">
        <a class="brand" href="#/dashboard">${brand()}</a>
        <nav>
          <a class="${route === "dashboard" ? "active" : ""}" href="#/dashboard">${icon("dashboard")} Dashboard</a>
          <a class="${route === "new" ? "active" : ""}" href="#/new">${icon("plus")} New analysis</a>
          <a class="${route === "history" || route === "analysis" ? "active" : ""}" href="#/history">${icon("history")} History</a>
        </nav>
        <div class="spacer"></div>
        <div class="userchip">
          <span class="avatar">${esc(initial)}</span>
          <div><strong>${esc(state.user.name)}</strong><small>${esc(state.user.email)}</small></div>
          <button class="icon-btn" type="button" data-action="logout" aria-label="Sign out">${icon("logout")}</button>
        </div>
      </aside>
      <div class="workspace">${content}<div id="toast" role="status"></div></div>
    </div>
    <div id="lightbox" hidden><button class="icon-btn light" type="button" data-action="close-lightbox" aria-label="Close">${icon("close")}</button><img alt="" /></div>`;
}

function statusTag(status) {
  if (status === "complete") return `<span class="tag">Complete</span>`;
  if (status === "failed") return `<span class="tag bad">Failed</span>`;
  return `<span class="tag wait">Running</span>`;
}

function recordCard(item, extra) {
  const thumb = item.thumb_url
    ? `<img src="${esc(item.thumb_url)}" alt="" />`
    : `<div class="ph">${item.status === "processing" ? "Running" : "No image"}</div>`;
  const mode = item.mode === "grid" ? `${item.rows}×${item.cols} mosaic` : "Single plate";
  const detail = [item.organism, mode, when(item.created_at)].filter(Boolean).join(" · ");
  return `
    <article class="record">
      <a href="#/analysis/${item.id}">${thumb}</a>
      <a href="#/analysis/${item.id}">
        <h3>${esc(item.title)}</h3>
        <div class="meta">${esc(detail)} ${statusTag(item.status)}</div>
      </a>
      <div class="record-side">
        <div class="count">${item.colony_count == null ? "—" : num(item.colony_count)}<small>colonies</small></div>
        ${extra || ""}
      </div>
    </article>`;
}

let renderToken = 0;
async function render() {
  const token = ++renderToken;
  stopPoll();
  clearPreviews();
  const route = current();
  const me = await api("/api/auth/me");
  if (token !== renderToken) return;
  if (me.ok) state.user = await me.json();
  else state.user = null;
  if (!state.user && route.name !== "login" && route.name !== "register") {
    location.hash = "#/login";
    return;
  }
  if (state.user && (route.name === "login" || route.name === "register")) {
    location.hash = "#/dashboard";
    return;
  }
  const titles = { login: "Sign in", register: "Create account", dashboard: "Dashboard", new: "New analysis", history: "History", analysis: "Analysis" };
  document.title = `${titles[route.name] || "Colonies"} · Microbial Colonies`;
  if (route.name === "login") paint(authScreen(false));
  else if (route.name === "register") paint(authScreen(true));
  else if (route.name === "dashboard") await showDashboard(token);
  else if (route.name === "new") paint(layout(newAnalysis()));
  else if (route.name === "history") await showHistory(token);
  else if (route.name === "analysis") await showAnalysis(route.id, token);
  else location.hash = "#/dashboard";
}

function paint(html, wire) {
  app.innerHTML = html;
  window.scrollTo(0, 0);
  if (wire) wire(app);
  else wirePage(app);
}

function authScreen(registering) {
  const google = state.config.google_client_id ? `<div class="or">or</div><div id="google-btn" class="google-slot"></div>` : "";
  const form = registering
    ? `<label class="field"><span>Name</span><input name="name" required minlength="2" autocomplete="name" /></label>
       <label class="field"><span>Email</span><input name="email" type="email" required autocomplete="email" /></label>
       <label class="field"><span>Password</span><input name="password" type="password" required minlength="8" autocomplete="new-password" /></label>
       <button class="btn primary" type="submit">Create account</button>
       <p class="switch">Already have an account? <a href="#/login">Sign in</a></p>`
    : `<label class="field"><span>Email</span><input name="email" type="email" required autocomplete="username" /></label>
       <label class="field"><span>Password</span><input name="password" type="password" required autocomplete="current-password" /></label>
       <button class="btn primary" type="submit">Sign in</button>
       <p class="switch">New here? <a href="#/register">Create an account</a></p>`;
  return `
    <section class="auth">
      <div class="auth-story">
        <a class="brand" href="#/login">${brand()}</a>
        <div>
          <h1>Count the plate.</h1>
          <p class="lede">One photograph, or a full stage scan. The count stays on your account.</p>
        </div>
      </div>
      <div class="auth-panel">
        <form class="auth-card" id="auth-form">
          <h2>${registering ? "Create an account" : "Sign in"}</h2>
          <p class="banner" id="auth-error" hidden></p>
          ${form}
          ${google}
        </form>
      </div>
    </section>`;
}

function wirePage(root) {
  const form = root.querySelector("#auth-form");
  if (form) wireAuth(form);
  const analysisForm = root.querySelector("#analysis-form");
  if (analysisForm) wireNew(root);
  const search = root.querySelector("#history-search");
  if (search) {
    search.addEventListener("submit", (event) => {
      event.preventDefault();
      const q = new FormData(search).get("q") || "";
      const mode = new FormData(search).get("mode") || "";
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (mode) params.set("mode", mode);
      location.hash = `#/history${params.toString() ? `?${params}` : ""}`;
    });
  }
  root.querySelectorAll("[data-heat]").forEach((button) => {
    const value = Number(button.dataset.heat);
    const max = Number(button.dataset.max || 1);
    const t = max ? value / max : 0;
    button.style.background = `color-mix(in srgb, #f4efe8 ${Math.round((1 - t) * 100)}%, #e7a07a)`;
  });
}

function mountGoogle(slot) {
  if (!slot || !state.config.google_client_id) return;
  let tries = 0;
  const attempt = () => {
    if (!slot.isConnected || tries > 20) return;
    tries += 1;
    if (!window.google?.accounts?.id) {
      setTimeout(attempt, 300);
      return;
    }
    google.accounts.id.initialize({
      client_id: state.config.google_client_id,
      callback: async (response) => {
        const res = await api("/api/auth/google", { method: "POST", json: { credential: response.credential } });
        if (!res.ok) {
          const error = rootError();
          if (error) {
            error.hidden = false;
            error.textContent = await readError(res);
          }
          return;
        }
        state.user = await res.json();
        location.hash = "#/dashboard";
      },
    });
    google.accounts.id.renderButton(slot, { theme: "outline", size: "large", text: "continue_with", shape: "pill", width: 360 });
  };
  attempt();
}

function rootError() {
  return document.getElementById("auth-error");
}

function wireAuth(form) {
  mountGoogle(form.querySelector("#google-btn"));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = form.querySelector("#auth-error");
    error.hidden = true;
    const data = Object.fromEntries(new FormData(form));
    const registering = current().name === "register";
    const res = await api(registering ? "/api/auth/register" : "/api/auth/login", { method: "POST", json: data });
    if (!res.ok) {
      error.hidden = false;
      error.textContent = await readError(res);
      return;
    }
    state.user = await res.json();
    location.hash = "#/dashboard";
  });
}

async function showDashboard(token) {
  const res = await api("/api/dashboard");
  if (token !== renderToken) return;
  if (!res.ok) {
    paint(layout(`<p class="banner">${esc(await readError(res))}</p>`));
    return;
  }
  const data = await res.json();
  if (token !== renderToken) return;
  const recent = data.recent.length
    ? data.recent.map((item) => recordCard(item)).join("")
    : `<div class="card empty"><h2>No plates yet</h2><p class="hint">Start with one image, or a 28-frame scan.</p><p><a class="btn primary" href="#/new">${icon("plus")} New analysis</a></p></div>`;
  paint(layout(`
    <header class="page-head">
      <div><h1>Dashboard</h1></div>
      <a class="btn primary" href="#/new">${icon("plus")} New analysis</a>
    </header>
    <section class="metrics">
      <article class="metric">${icon("plate")}<span>Completed</span><strong>${num(data.analyses)}</strong></article>
      <article class="metric">${icon("grid")}<span>Colonies</span><strong>${num(data.colonies)}</strong></article>
      <article class="metric">${icon("dashboard")}<span>Average</span><strong>${data.mean_colonies == null ? "—" : num(data.mean_colonies)}</strong></article>
      <article class="metric">${icon("history")}<span>Running</span><strong>${num(data.processing)}</strong></article>
    </section>
    <section class="card">
      <div class="section-title"><h2>Recent</h2><a href="#/history">History</a></div>
      <div class="stack">${recent}</div>
    </section>`));
}

function suggestGrid(count) {
  if (count === 28) return { rows: 7, cols: 4, layout: "scanner" };
  let best = { rows: 1, cols: count, layout: "row" };
  let score = Infinity;
  for (let rows = 1; rows <= Math.sqrt(count); rows += 1) {
    if (count % rows) continue;
    const cols = count / rows;
    const next = Math.abs(cols - rows);
    if (next < score) {
      score = next;
      best = { rows, cols, layout: "row" };
    }
  }
  return best;
}

function slots(rows, cols, layout) {
  const grid = Array.from({ length: rows }, () => Array(cols).fill(null));
  let number = 1;
  if (layout === "scanner") {
    for (let col = 0; col < cols; col += 1) {
      const rowsOrder = [];
      for (let row = 0; row < rows; row += 1) rowsOrder.push(row);
      if (col % 2 === 1) rowsOrder.reverse();
      rowsOrder.forEach((row) => { grid[row][col] = number; number += 1; });
    }
  } else {
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) grid[row][col] = number++;
    }
  }
  return grid;
}

function newAnalysis() {
  return `
    <header class="page-head">
      <div><h1>New analysis</h1></div>
    </header>
    <form id="analysis-form" class="stack">
      <div class="modes">
        <label class="mode"><input type="radio" name="mode" value="single" />${icon("image")}<span class="mode-copy"><strong>Single plate</strong><small>One image, boxes, and a count.</small></span></label>
        <label class="mode"><input type="radio" name="mode" value="grid" checked />${icon("grid")}<span class="mode-copy"><strong>Mosaic</strong><small>Set the count, rows, and columns, then stitch.</small></span></label>
      </div>
      <div class="card stack">
        <div class="form-grid">
          <label class="field"><span>Sample name</span><input name="title" placeholder="Plate A, 24 h" /></label>
          <label class="field"><span>Organism</span><input name="organism" list="organisms" placeholder="E. coli" /></label>
          <datalist id="organisms"><option value="E. coli"></option><option value="S. aureus"></option><option value="Mixed culture"></option></datalist>
          <label class="field"><span>Confidence</span><input name="confidence" type="number" min="0.05" max="0.95" step="0.05" value="0.25" /></label>
          <label class="field"><span>Notes</span><input name="notes" placeholder="Medium, dilution, time" /></label>
        </div>
        <div id="grid-controls" class="stack">
          <div class="pills">
            <button class="pill" type="button" data-preset="28">28 · 7×4 scanner</button>
            <button class="pill" type="button" data-preset="20">20 · 5×4</button>
            <button class="pill" type="button" data-preset="16">16 · 4×4</button>
            <button class="pill" type="button" data-preset="12">12 · 3×4</button>
          </div>
          <div class="form-grid">
            <label class="field"><span>Pictures</span><input name="count" type="number" min="1" max="64" value="28" /></label>
            <label class="field"><span>Rows</span><input name="rows" type="number" min="1" max="16" value="7" /></label>
            <label class="field"><span>Columns</span><input name="cols" type="number" min="1" max="16" value="4" /></label>
            <label class="field"><span>Placement</span>
              <select name="layout">
                <option value="scanner" selected>Scanner path</option>
                <option value="row">Row by row</option>
              </select>
            </label>
          </div>
          <p class="hint" id="layout-note"></p>
          <div id="slotmap"></div>
        </div>
        <label class="drop" id="drop">
          <input class="file-input" id="files" type="file" accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff" multiple />
          ${icon("image")}
          <strong>Drop images here, or browse</strong>
          <span class="hint" id="file-count">No images yet</span>
        </label>
        <label class="check"><input type="checkbox" name="sort_by_name" checked /> Sort by file name (1, 2, 10)</label>
        <div class="thumbs" id="thumbs"></div>
        <p class="banner" id="form-error" hidden></p>
        <div class="btn-row"><button class="btn primary" id="run" type="submit">${icon("plus")} <span>Run detection</span></button></div>
      </div>
    </form>`;
}

function wireNew(root) {
  const form = root.querySelector("#analysis-form");
  let files = [];
  const fileInput = root.querySelector("#files");
  const drop = root.querySelector("#drop");

  function mode() {
    return form.querySelector('input[name="mode"]:checked').value;
  }
  function ordered() {
    const copy = [...files];
    if (form.sort_by_name.checked) {
      copy.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
    }
    return copy;
  }
  function paintBuilder() {
    const grid = mode() === "grid";
    root.querySelector("#grid-controls").hidden = !grid;
    fileInput.multiple = grid;
    const chosen = ordered();
    root.querySelector("#file-count").textContent = chosen.length
      ? `${chosen.length} image${chosen.length === 1 ? "" : "s"} selected`
      : "No images yet";
    const thumbs = root.querySelector("#thumbs");
    clearPreviews();
    thumbs.innerHTML = chosen.map((file, index) => {
      const url = URL.createObjectURL(file);
      state.previews.push(url);
      return `<div class="thumb"><img src="${url}" alt="" /><button type="button" data-remove="${index}" aria-label="Remove ${esc(file.name)}">×</button></div>`;
    }).join("");
    if (!grid) return;
    const rows = Number(form.rows.value);
    const cols = Number(form.cols.value);
    const count = Number(form.count.value);
    const note = root.querySelector("#layout-note");
    const mismatch = rows * cols !== count;
    note.className = mismatch ? "hint warn" : "hint";
    note.textContent = mismatch
      ? `Rows × columns is ${rows * cols}. The picture count is ${count}. Those have to match.`
      : (form.layout.value === "scanner"
        ? "Numbers follow capture order. Even columns go down, odd columns go up — the same path as the 7×4 stage."
        : "Numbers follow capture order, filled left to right, then the next row.");
    if (!(rows >= 1 && cols >= 1 && rows <= 16 && cols <= 16)) {
      root.querySelector("#slotmap").innerHTML = "";
      return;
    }
    const map = slots(rows, cols, form.layout.value);
    root.querySelector("#slotmap").innerHTML = `<div class="slotmap" style="grid-template-columns: repeat(${cols}, minmax(0, 1fr))">${
      map.flat().map((n) => {
        const file = chosen[n - 1];
        return `<div class="slot ${file ? "filled" : ""}"><strong>${n}</strong>${file ? `<em>${esc(file.name)}</em>` : ""}</div>`;
      }).join("")
    }</div>`;
  }

  form.querySelectorAll('input[name="mode"]').forEach((input) => input.addEventListener("change", () => {
    if (mode() === "single" && files.length > 1) files = files.slice(0, 1);
    paintBuilder();
  }));
  ["count", "rows", "cols", "layout", "sort_by_name"].forEach((name) => {
    form[name].addEventListener("input", paintBuilder);
    form[name].addEventListener("change", paintBuilder);
  });
  root.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click", () => {
    const count = Number(button.dataset.preset);
    const grid = count === 28 ? { rows: 7, cols: 4, layout: "scanner" } : { ...suggestGrid(count), layout: "row" };
    if (count === 20) Object.assign(grid, { rows: 5, cols: 4, layout: "row" });
    if (count === 12) Object.assign(grid, { rows: 3, cols: 4, layout: "row" });
    form.count.value = String(count);
    form.rows.value = String(grid.rows);
    form.cols.value = String(grid.cols);
    form.layout.value = grid.layout;
    form.querySelector('input[name="mode"][value="grid"]').checked = true;
    paintBuilder();
  }));

  function addFiles(list) {
    const images = [...list].filter((file) => file.type.startsWith("image/") || /\.(jpe?g|png|webp|bmp|tiff?)$/i.test(file.name));
    if (mode() === "single") files = images.slice(0, 1);
    else files = files.concat(images).slice(0, 64);
    paintBuilder();
  }
  fileInput.addEventListener("change", () => {
    addFiles(fileInput.files);
    fileInput.value = "";
  });
  drop.addEventListener("dragover", (event) => { event.preventDefault(); drop.classList.add("hot"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("hot"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("hot");
    addFiles(event.dataTransfer.files);
  });
  root.querySelector("#thumbs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove]");
    if (!button) return;
    const target = ordered()[Number(button.dataset.remove)];
    files = files.filter((file) => file !== target);
    paintBuilder();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = root.querySelector("#form-error");
    error.hidden = true;
    const chosen = ordered();
    const selected = mode();
    if (selected === "single" && chosen.length !== 1) {
      error.hidden = false;
      error.textContent = "Add one image for a single plate.";
      return;
    }
    if (selected === "grid") {
      const rows = Number(form.rows.value);
      const cols = Number(form.cols.value);
      const count = Number(form.count.value);
      if (rows * cols !== count) {
        error.hidden = false;
        error.textContent = `Set rows × columns equal to the picture count. ${rows}×${cols} is ${rows * cols}, and the count is ${count}.`;
        return;
      }
      if (chosen.length !== count) {
        error.hidden = false;
        error.textContent = `This mosaic needs ${count} images. ${chosen.length} are selected.`;
        return;
      }
    }
    const body = new FormData();
    body.set("title", form.title.value);
    body.set("organism", form.organism.value);
    body.set("notes", form.notes.value);
    body.set("mode", selected);
    body.set("layout", selected === "grid" ? form.layout.value : "row");
    body.set("rows", selected === "grid" ? form.rows.value : "1");
    body.set("cols", selected === "grid" ? form.cols.value : "1");
    body.set("confidence", form.confidence.value);
    body.set("imgsz", "1280");
    body.set("sort_by_name", form.sort_by_name.checked ? "true" : "false");
    chosen.forEach((file) => body.append("files", file));
    const button = root.querySelector("#run");
    const label = button.querySelector("span");
    button.disabled = true;
    label.textContent = "Uploading…";
    const res = await api("/api/analyses", { method: "POST", body });
    if (!res.ok) {
      button.disabled = false;
      label.textContent = "Run detection";
      error.hidden = false;
      error.textContent = await readError(res);
      return;
    }
    const created = await res.json();
    location.hash = `#/analysis/${created.id}`;
  });
  paintBuilder();
}

async function showHistory(token) {
  const route = current();
  const params = new URLSearchParams(route.query);
  if (!params.has("limit")) params.set("limit", "12");
  const res = await api(`/api/analyses?${params}`);
  if (token !== renderToken) return;
  if (!res.ok) {
    paint(layout(`<p class="banner">${esc(await readError(res))}</p>`));
    return;
  }
  const data = await res.json();
  if (token !== renderToken) return;
  const q = route.query.get("q") || "";
  const mode = route.query.get("mode") || "";
  const offset = Number(route.query.get("offset") || 0);
  const list = data.items.length
    ? data.items.map((item) => recordCard(item, `<button class="icon-btn danger" type="button" data-action="delete-analysis" data-id="${item.id}" aria-label="Delete">${icon("trash")}</button>`)).join("")
    : `<div class="card empty"><h2>Nothing in this view</h2><p class="hint">Runs from this account show up here.</p></div>`;
  const prev = Math.max(0, offset - 12);
  const next = offset + 12;
  paint(layout(`
    <header class="page-head"><div><h1>History</h1><p class="lede">${num(data.total)} ${data.total === 1 ? "record" : "records"}</p></div><a class="btn primary" href="#/new">${icon("plus")} New analysis</a></header>
    <form class="filters" id="history-search">
      <label class="search">${icon("search")}<input type="search" name="q" value="${esc(q)}" placeholder="Sample, organism, notes" /></label>
      <select name="mode">
        <option value="" ${mode === "" ? "selected" : ""}>All types</option>
        <option value="single" ${mode === "single" ? "selected" : ""}>Single plate</option>
        <option value="grid" ${mode === "grid" ? "selected" : ""}>Mosaic</option>
      </select>
      <button class="btn ghost" type="submit">Search</button>
    </form>
    <div class="stack">${list}</div>
    <div class="pager">
      ${offset > 0 ? `<a class="btn ghost" href="#/history?${historyQuery(route.query, { offset: prev })}">Previous</a>` : "<span></span>"}
      ${next < data.total ? `<a class="btn ghost" href="#/history?${historyQuery(route.query, { offset: next })}">Next</a>` : ""}
    </div>`));
}

function historyQuery(query, patch) {
  const next = new URLSearchParams(query);
  Object.entries(patch).forEach(([key, value]) => next.set(key, String(value)));
  return next.toString();
}

async function showAnalysis(id, token) {
  const res = await api(`/api/analyses/${id}`);
  if (token !== renderToken) return;
  if (res.status === 401) {
    location.hash = "#/login";
    return;
  }
  if (!res.ok) {
    paint(layout(`<p class="banner">${esc(await readError(res))}</p>`));
    return;
  }
  const data = await res.json();
  if (token !== renderToken) return;
  paint(layout(analysisView(data)), (root) => wireAnalysis(root, data));
  if (data.status === "processing") {
    state.poll = setInterval(async () => {
      const follow = await api(`/api/analyses/${id}`);
      if (!follow.ok || current().id !== id) return;
      const latest = await follow.json();
      const bar = document.querySelector("[data-progress]");
      const label = document.querySelector("[data-progress-label]");
      if (latest.status === "processing" && bar && label) {
        bar.style.width = `${latest.progress}%`;
        label.textContent = latest.progress_message;
        return;
      }
      stopPoll();
      render();
    }, 1200);
  }
}

function analysisView(data) {
  if (data.status === "processing") {
    return `
      <header class="page-head"><div><p class="hint"><a href="#/history">History</a></p><h1>${esc(data.title)}</h1></div>${statusTag(data.status)}</header>
      <section class="card processing">
        <div class="dish" aria-hidden="true"></div>
        <h2 data-progress-label>${esc(data.progress_message)}</h2>
        <div class="progress" style="width:min(420px, 100%)"><span data-progress style="width:${data.progress}%"></span></div>
        <p class="hint">Frames are counted one plate at a time. You can leave this page; the run keeps going.</p>
      </section>`;
  }
  if (data.status === "failed") {
    return `
      <header class="page-head"><div><p class="hint"><a href="#/history">History</a></p><h1>${esc(data.title)}</h1></div></header>
      <p class="banner">${esc(data.error || "This run failed.")}</p>`;
  }
  const max = Math.max(1, ...data.tiles.map((tile) => tile.colony_count));
  const heat = data.mode === "grid" ? `
    <div class="card">
      <h2>Tiles</h2>
      <p class="hint">Shading follows the count on each frame. The plate total is the sum.</p>
      <div class="heat" style="grid-template-columns: repeat(${data.cols}, minmax(0, 1fr)); margin-top: 12px">
        ${heatCells(data, max)}
      </div>
    </div>` : "";
  const first = data.tiles[0];
  const rows = (first ? first.detections.slice(0, 40) : []).map((det) => `
    <tr><td>${det.index}</td><td>${esc(det.class_name)}</td><td>${det.confidence.toFixed(2)}</td><td>${Math.round(det.x1)}, ${Math.round(det.y1)}</td></tr>`).join("");
  return `
    <header class="page-head">
      <div>
        <p class="hint"><a href="#/history">History</a></p>
        <h1>${esc(data.title)}</h1>
        ${data.organism || data.notes ? `<p class="lede">${esc([data.organism, data.notes].filter(Boolean).join(" · "))}</p>` : ""}
      </div>
      <div class="btn-row">
        <a class="btn ghost" href="/api/analyses/${data.id}/export.csv">${icon("download")} CSV</a>
        <button class="btn danger" type="button" data-action="delete-analysis" data-id="${data.id}">${icon("trash")} Delete</button>
      </div>
    </header>
    <section class="split">
      <figure class="hero-figure">
        <img id="hero" alt="Annotated plate" src="${esc(data.annotated_url || "")}" data-action="lightbox" data-src="${esc(data.annotated_url || "")}" />
      </figure>
      <aside class="card">
        <span class="hint">Colonies</span>
        <div class="hero-count">${num(data.colony_count)}</div>
        <p class="hint">${data.mode === "grid" ? "Sum of the tile counts." : "Boxes on this plate."}</p>
        <div class="btn-row view-toggle">
          <button class="btn ghost" type="button" data-view="annotated">${icon(data.mode === "grid" ? "grid" : "plate")} ${data.mode === "grid" ? "Plate" : "Annotated"}</button>
          <button class="btn ghost" type="button" data-view="original">${icon("image")} Original</button>
        </div>
        <dl class="stat-list">
          <div><dt>Operator</dt><dd>${esc(data.operator)}</dd></div>
          <div><dt>Started</dt><dd>${when(data.created_at)}</dd></div>
          <div><dt>Runtime</dt><dd>${duration(data.duration_ms)}</dd></div>
          <div><dt>Threshold</dt><dd>${data.confidence}</dd></div>
          <div><dt>Mean score</dt><dd>${data.mean_confidence == null ? "—" : data.mean_confidence.toFixed(2)}</dd></div>
          <div><dt>Layout</dt><dd>${data.mode === "grid" ? `${data.rows}×${data.cols} ${data.layout === "scanner" ? "scanner" : "rows"}` : "Single"}</dd></div>
        </dl>
      </aside>
    </section>
    ${heat}
    <section class="card" style="margin-top:16px">
      <div class="section-title"><h2 id="det-title">Detections${data.mode === "grid" ? " · tile 1" : ""}</h2></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Class</th><th>Confidence</th><th>Position</th></tr></thead>
          <tbody id="det-body">${rows || `<tr><td colspan="4">No colonies at this threshold.</td></tr>`}</tbody>
        </table>
      </div>
      <p class="hint" id="det-more"></p>
    </section>`;
}

function heatCells(data, max) {
  const byCapture = new Map(data.tiles.map((tile) => [tile.index + 1, tile]));
  const map = slots(data.rows, data.cols, data.layout || "row");
  return map.flat().map((number) => {
    const tile = byCapture.get(number);
    const count = tile ? tile.colony_count : 0;
    return `<button type="button" data-heat="${count}" data-max="${max}" data-tile="${tile ? tile.index : 0}">${number}<br />${count}</button>`;
  }).join("");
}

function wireAnalysis(root, data) {
  const hero = root.querySelector("#hero");
  function show(url, title) {
    if (!hero || !url) return;
    hero.src = url;
    hero.dataset.src = url;
    const heading = root.querySelector("#det-title");
    if (heading && title) heading.textContent = title;
  }
  function showTile(index) {
    const tile = data.tiles.find((item) => item.index === index) || data.tiles[0];
    if (!tile) return;
    show(tile.annotated_url, data.mode === "grid" ? `Detections · tile ${tile.index + 1}` : "Detections");
    const body = root.querySelector("#det-body");
    const more = root.querySelector("#det-more");
    if (!body) return;
    const visible = tile.detections.slice(0, 40);
    body.innerHTML = visible.length
      ? visible.map((det) => `<tr><td>${det.index}</td><td>${esc(det.class_name)}</td><td>${det.confidence.toFixed(2)}</td><td>${Math.round(det.x1)}, ${Math.round(det.y1)}</td></tr>`).join("")
      : `<tr><td colspan="4">No colonies on this tile.</td></tr>`;
    if (more) more.textContent = tile.detections.length > 40 ? `Showing 40 of ${tile.detections.length}. The CSV has every box.` : "";
  }
  root.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
    const heading = root.querySelector("#det-title");
    if (button.dataset.view === "original") {
      show(data.original_url);
      if (heading) heading.textContent = "Detections";
      return;
    }
    if (data.tiles[0] && data.mode === "single") showTile(0);
    else show(data.annotated_url, data.mode === "grid" ? "Detections · tile 1" : "Detections");
  }));
  root.querySelectorAll("[data-tile]").forEach((button) => button.addEventListener("click", () => showTile(Number(button.dataset.tile))));
  if (data.tiles[0] && data.tiles[0].detections.length > 40) {
    const more = root.querySelector("#det-more");
    if (more) more.textContent = `Showing 40 of ${data.tiles[0].detections.length}. The CSV has every box.`;
  }
  wirePage(root);
}

function openLightbox(src) {
  const box = document.getElementById("lightbox");
  if (!box || !src) return;
  box.querySelector("img").src = src;
  box.hidden = false;
}

function closeLightbox() {
  const box = document.getElementById("lightbox");
  if (box) box.hidden = true;
}

document.body.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  if (button.dataset.action === "logout") {
    await api("/api/auth/logout", { method: "POST" });
    state.user = null;
    location.hash = "#/login";
    return;
  }
  if (button.dataset.action === "close-lightbox") closeLightbox();
  if (button.dataset.action === "lightbox") openLightbox(button.dataset.src);
  if (button.dataset.action === "delete-analysis") {
    if (!confirm("Delete this analysis? The images and counts will be removed from your account.")) return;
    const res = await api(`/api/analyses/${button.dataset.id}`, { method: "DELETE" });
    if (!res.ok) {
      toast(await readError(res));
      return;
    }
    toast("Analysis deleted");
    if (current().name === "analysis") location.hash = "#/history";
    else render();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeLightbox();
});

window.addEventListener("hashchange", () => { render(); });

async function boot() {
  try {
    const configRes = await fetch("/api/auth/config");
    state.config = await configRes.json();
    const me = await fetch("/api/auth/me", { credentials: "include" });
    if (me.ok) state.user = await me.json();
  } catch (_err) {
    app.innerHTML = `<div class="auth-panel"><p class="banner">The application server is not responding.</p></div>`;
    return;
  }
  if (!location.hash) location.hash = state.user ? "#/dashboard" : "#/login";
  else render();
}

boot();
