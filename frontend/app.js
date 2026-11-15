// ClipForge frontend: no build step, plain ES modules.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const view = $("#view");
let INFO = null;
let FOLDERS = [];
let pollTimer = null;

// ================================================================= icons ==
const P = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
  folderPlus: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/><path d="M12 11v6M9 14h6"/>',
  inbox: '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5.5 5h13L21 13v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  plug: '<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z"/>',
  sidebar: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4L12 5.6"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4L12 18.4"/>',
  upload: '<path d="M12 15V3M7 8l5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M14 6l4 4"/>',
  move: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/><path d="M10 14h6M13.5 11.5 16 14l-2.5 2.5"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 20v-4h-4"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4M3 12h18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  flame: '<path d="M12 22c4 0 7-2.7 7-6.8 0-3.6-2.4-6-4-8.2-.5 2-1.7 3-3 3 .5-3-1-6-4-8 .2 3-2 5.6-3.4 7.7A8 8 0 0 0 5 15.2C5 19.3 8 22 12 22z"/>',
  game: '<rect x="2" y="7" width="20" height="11" rx="5"/><path d="M7 11v3M5.5 12.5h3M15.5 12h.01M18 13.5h.01"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  cc: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10.5 10.2a2.2 2.2 0 1 0 0 3.6M17 10.2a2.2 2.2 0 1 0 0 3.6"/>',
  crop: '<path d="M6 2v14a2 2 0 0 0 2 2h14M2 6h14a2 2 0 0 1 2 2v14"/>',
  play: '<path d="M7 4.5v15l13-7.5z"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.1 8.1 20 20M8.1 15.9 20 4"/>',
  star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
  hash: '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M3 3l18 18M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A16.5 16.5 0 0 0 2 12s3.6 7 10 7a9.9 9.9 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  logout: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l-5-5 5-5M5 12h11"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20M6 15h4"/>',
  send: '<path d="M21 3 10 14"/><path d="M21 3l-7 18-4-7-7-4z"/>',
  drive: '<path d="M8 3h8l6 10-4 7H6l-4-7z"/><path d="M8 3l6 10h8M2 13h12l-4 7"/>',
};
const icon = (n, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ""}</svg>`;

// platform marks (simplified glyphs, filled)
const PLATFORMS = {
  youtube: { name: "YouTube", color: "#ff0033", bg: "#2a0a0f",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="4.5" fill="#ff0033"/><path d="M10 9v6l5.2-3z" fill="#fff"/></svg>' },
  tiktok: { name: "TikTok", color: "#25f4ee", bg: "#0d1f20",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.2 3h3c.2 1.9 1.6 3.4 3.6 3.6v3a7 7 0 0 1-3.6-1.1v6.3a5.8 5.8 0 1 1-5.8-5.8c.3 0 .6 0 .9.1v3.1a2.7 2.7 0 1 0 1.9 2.6z" fill="#fff"/><path d="M13.2 4h1c.2 1.9 1.6 3.4 3.6 3.6" stroke="#25f4ee" fill="none" stroke-width=".8"/></svg>' },
  instagram: { name: "Instagram", color: "#e1306c", bg: "#2a0c1b",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="igg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#feda75"/><stop offset=".35" stop-color="#fa7e1e"/><stop offset=".65" stop-color="#d62976"/><stop offset="1" stop-color="#4f5bd5"/></linearGradient></defs><rect x="3" y="3" width="18" height="18" rx="5.5" fill="none" stroke="url(#igg)" stroke-width="2.2"/><circle cx="12" cy="12" r="4.2" fill="none" stroke="url(#igg)" stroke-width="2.2"/><circle cx="17.3" cy="6.7" r="1.3" fill="#d62976"/></svg>' },
  x: { name: "X", color: "#e7e7e7", bg: "#1c1c1f",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 3.5h5.2l11.8 17h-5.2z" fill="#fff"/><path d="M19.6 3.5 13.3 10.6M4.4 20.5l6.4-7.1" stroke="#fff" stroke-width="1.9"/></svg>' },
  twitch: { name: "Twitch", color: "#9146ff", bg: "#1b1030",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3 3.5 6.5V19H8v2.5h2.5L13 19h3.5l4.5-4.5V3z" fill="#9146ff"/><path d="M11 7.5v4.5M15.5 7.5v4.5" stroke="#fff" stroke-width="1.8"/></svg>' },
  facebook: { name: "Facebook", color: "#1877f2", bg: "#0c1a2e",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="#1877f2"/><path d="M13.2 21v-7h2.4l.4-2.8h-2.8V9.4c0-.8.3-1.4 1.4-1.4H16V5.6a17 17 0 0 0-2.2-.1c-2.2 0-3.6 1.3-3.6 3.7v2H7.8V14h2.4v7z" fill="#fff"/></svg>' },
  vimeo: { name: "Vimeo", color: "#1ab7ea", bg: "#0b2029",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.5 7.6c-.1 1.9-1.4 4.4-3.9 7.6-2.6 3.3-4.8 5-6.6 5-1.1 0-2.1-1-2.8-3.1L6.6 11.8C6.1 9.7 5.5 8.7 4.9 8.7c-.1 0-.6.3-1.4.9l-.9-1.1L5.4 6c1.2-1.1 2.2-1.6 2.8-1.7 1.5-.1 2.4.9 2.7 3 .4 2.3.6 3.8.8 4.3.4 1.9.9 2.9 1.4 2.9.4 0 1-.6 1.9-1.9.9-1.3 1.3-2.3 1.4-3 .1-1.1-.3-1.7-1.4-1.7-.5 0-1 .1-1.5.3 1-3.3 2.9-4.9 5.8-4.8 2.1.1 3.1 1.4 2.9 4.2z" fill="#1ab7ea"/></svg>' },
  drive: { name: "Google Drive", color: "#1fa463", bg: "#0b2015",
    svg: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.3 3h7.4l6.3 11h-7.4z" fill="#ffc107"/><path d="M8.3 3 2 14l3.7 6.5L12 9.5z" fill="#1fa463"/><path d="M5.7 20.5h12.6L22 14H9.4z" fill="#4285f4"/></svg>' },
  upload: { name: "Upload", color: "#a1a1aa", bg: "#1d1d20", svg: icon("upload") },
  web: { name: "Web link", color: "#a1a1aa", bg: "#1d1d20", svg: icon("link") },
};
const plat = id => PLATFORMS[id] || PLATFORMS.web;
const platSvg = (id, size = 18) => plat(id).svg.replace("<svg", `<svg width="${size}" height="${size}"`);

function hydrateIcons(root = document) {
  $$("[data-icon]", root).forEach(el => {
    if (el.dataset.hydrated) return;
    el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon));
    el.dataset.hydrated = "1";
  });
}

// =============================================================== helpers ==
const api = async (path, opts = {}) => {
  const isForm = opts.body instanceof FormData;
  const res = await fetch(path, {
    ...opts,
    headers: opts.body && !isForm ? { "content-type": "application/json" } : {},
    body: opts.body && !isForm ? JSON.stringify(opts.body) : opts.body,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/") && !opts._retried && SB) {
    try {
      const { data } = await SB.auth.refreshSession();
      if (data?.session) { await syncSession(data.session); return api(path, { ...opts, _retried: true }); }
    } catch {}
  }
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    ME = null;
    if (!/^(#\/?)?$|^#\/(signin|signup|forgot|reset)$/.test(location.hash)) { lsSet("clipforge.next", location.hash); location.hash = "#/signin"; }
    throw new Error("Please sign in to continue.");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const d = (await res.json()).detail; msg = typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : msg; } catch {}
    throw new Error(msg || `Request failed (${res.status})`);
  }
  return res.json();
};
const esc = (s = "") => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = t => { t = Math.max(0, t || 0); const m = Math.floor(t / 60); const s = (t % 60).toFixed(1).padStart(4, "0"); return `${m}:${s}`; };
const dur = t => { t = Math.round(t || 0); const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60; return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`; };
const num = n => n == null ? "—" : n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e4 ? `${(n / 1e3).toFixed(n >= 1e5 ? 0 : 1)}K` : Number(n).toLocaleString();
const ago = ts => { const s = Date.now() / 1000 - ts; if (s < 60) return "just now"; if (s < 3600) return `${Math.floor(s / 60)}m ago`; if (s < 86400) return `${Math.floor(s / 3600)}h ago`; if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`; return new Date(ts * 1000).toLocaleDateString(); };
const slug = s => (s || "clip").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "clip";
function toast(msg, ms = 2800, err = false) { const t = $("#toast"); t.textContent = msg; t.classList.toggle("err", err); t.classList.add("show"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms); }
const fail = e => {
  const msg = e.message || String(e);
  toast(msg, /Plans page|Upgrade/.test(msg) ? 8000 : 5000, true);
  $("#toast").onclick = /Plans page|Upgrade/.test(msg) ? () => { location.hash = "#/billing"; } : null;
};
const lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
const folderById = id => FOLDERS.find(f => f.id === id);
async function loadFolders() { try { FOLDERS = await api("/api/folders"); } catch { FOLDERS = []; } return FOLDERS; }
function setCrumbs(parts) {
  $("#crumbs").innerHTML = parts.map((p, i) => i === parts.length - 1 ? `<strong>${esc(p.label)}</strong>` : `<a href="${p.href}">${esc(p.label)}</a><span class="dim">/</span>`).join("");
}

// ---------------------------------------------------------------- modal --
function openModal(html, onMount, cls = "") {
  const d = $("#modal"), body = $("#modal-body");
  body.className = `modal ${cls}`;
  body.innerHTML = html; hydrateIcons(body);
  return new Promise(resolve => {
    let done = false;
    const finish = v => { if (done) return; done = true; d.close(); resolve(v); };
    d.onclose = () => finish(null);
    body.querySelectorAll("[data-close]").forEach(b => b.onclick = () => finish(null));
    d.showModal();
    onMount?.(body, finish);
  });
}
function confirmBox(title, text, okLabel = "Delete", danger = true) {
  return openModal(`
    <div class="modal-head"><h2>${esc(title)}</h2></div>
    <p class="muted">${esc(text)}</p>
    <div class="row end"><button class="btn ghost" data-close>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" id="m-ok">${esc(okLabel)}</button></div>`,
    (b, finish) => { const ok = $("#m-ok", b); ok.onclick = () => finish(true); ok.focus(); });
}
function folderForm(title, folder = {}) {
  const colors = ["#c6f432", "#5eead4", "#a78bfa", "#f472b6", "#fbbf24", "#60a5fa", "#fb7185"];
  let color = folder.color || colors[FOLDERS.length % colors.length];
  return openModal(`
    <div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" data-close aria-label="Close" data-icon="x"></button></div>
    <form id="m-form">
      <label>Folder name<input id="m-name" maxlength="40" required value="${esc(folder.name || "")}" placeholder="e.g. GTA 6 streams" /></label>
      <label>Color</label>
      <div class="swatches" role="radiogroup" aria-label="Folder color">${colors.map(c => `<button type="button" data-c="${c}" style="background:${c}" aria-label="${c}" aria-pressed="${c === color}"></button>`).join("")}</div>
      <div class="row end" style="margin-top:20px"><button type="button" class="btn ghost" data-close>Cancel</button><button class="btn primary">${folder.id ? "Save" : "Create folder"}</button></div>
    </form>`,
    (b, finish) => {
      const name = $("#m-name", b); name.focus(); name.select();
      $(".swatches", b).onclick = e => { const s = e.target.closest("[data-c]"); if (!s) return; color = s.dataset.c; $$(".swatches button", b).forEach(x => x.setAttribute("aria-pressed", x === s)); };
      $("#m-form", b).onsubmit = e => { e.preventDefault(); if (name.value.trim()) finish({ name: name.value.trim(), color }); };
    });
}
function textPrompt(title, label, value = "") {
  return openModal(`
    <div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" data-close aria-label="Close" data-icon="x"></button></div>
    <form id="m-form"><label>${esc(label)}<input id="m-val" maxlength="80" required value="${esc(value)}" /></label>
    <div class="row end"><button type="button" class="btn ghost" data-close>Cancel</button><button class="btn primary">Save</button></div></form>`,
    (b, finish) => { const i = $("#m-val", b); i.focus(); i.select(); $("#m-form", b).onsubmit = e => { e.preventDefault(); if (i.value.trim()) finish(i.value.trim()); }; });
}
function pickFolder(currentId) {
  return openModal(`
    <div class="modal-head"><h2>Move to folder</h2><button class="icon-btn" data-close aria-label="Close" data-icon="x"></button></div>
    <div class="pick-list">
      <button data-f="" aria-current="${!currentId}">${icon("inbox")} Unsorted</button>
      ${FOLDERS.map(f => `<button data-f="${f.id}" aria-current="${f.id === currentId}"><span class="fdot" style="background:${f.color}"></span>${esc(f.name)}</button>`).join("")}
    </div>
    <button class="btn ghost sm" id="m-new">${icon("folderPlus")} New folder</button>`,
    (b, finish) => {
      $(".pick-list", b).onclick = e => { const x = e.target.closest("[data-f]"); if (x) finish({ id: x.dataset.f }); };
      $("#m-new", b).onclick = () => finish({ create: true });
    });
}

// ----------------------------------------------------------------- menu --
function showMenu(anchor, items) {
  const m = $("#menu");
  m.innerHTML = items.map((it, i) => it === "-" ? "<hr>" : it.header != null ? `<div class="menu-head"><b>${esc(it.header)}</b><small>${esc(it.sub || "")}</small></div>` : `<button role="menuitem" data-i="${i}" class="${it.danger ? "danger" : ""}">${icon(it.icon)}${esc(it.label)}</button>`).join("");
  m.hidden = false;
  const r = anchor.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
  m.style.left = `${Math.max(8, Math.min(r.right - mw, innerWidth - mw - 8))}px`;
  m.style.top = `${r.bottom + mh + 6 > innerHeight ? r.top - mh - 6 : r.bottom + 6}px`;
  m.querySelector("button")?.focus();
  const close = () => { m.hidden = true; document.removeEventListener("mousedown", out, true); document.removeEventListener("keydown", key, true); };
  const out = e => { if (!m.contains(e.target)) close(); };
  const key = e => {
    if (e.key === "Escape") { close(); anchor.focus(); }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); const bs = $$("button", m), i = bs.indexOf(document.activeElement); bs[(i + (e.key === "ArrowDown" ? 1 : -1) + bs.length) % bs.length].focus(); }
  };
  setTimeout(() => { document.addEventListener("mousedown", out, true); document.addEventListener("keydown", key, true); });
  m.onclick = e => { const b = e.target.closest("[data-i]"); if (!b) return; close(); items[+b.dataset.i].run(); };
}

// -------------------------------------------------------------- tooltip --
function bindTips(root) {
  const tip = $("#tip");
  root.addEventListener("mousemove", e => {
    const t = e.target.closest("[data-tip]");
    if (!t) { tip.hidden = true; return; }
    tip.innerHTML = t.dataset.tip; tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.min(e.clientX + 14, innerWidth - w - 8)}px`;
    tip.style.top = `${Math.max(8, e.clientY - h - 12)}px`;
  });
  root.addEventListener("mouseleave", () => { tip.hidden = true; });
}

// =========================================================== AI settings ==
const LS = "clipforge.llm";
const loadLLM = () => lsGet(LS, null) || { provider: "anthropic" };
const saveLLM = v => lsSet(LS, v);
function llmPayload() {
  const s = loadLLM();
  if (s.provider === "anthropic") return { provider: "anthropic", api_key: s.key || "", model: s.model || "" };
  if (s.provider === "openai_compat") return { provider: "openai_compat", base_url: s.base || "", api_key: s.okey || "", model: s.model || "" };
  return { provider: "none" };
}
function llmReady() { const s = loadLLM(); return (s.provider === "anthropic" && !!s.key) || (s.provider === "openai_compat" && !!s.base && !!s.model); }
function refreshPill() {
  const s = loadLLM(), pill = $("#ai-pill");
  let label = "AI: signals only", on = false;
  if (s.provider === "anthropic" && s.key) { label = `Claude · ${s.model || INFO?.default_anthropic_model || "default"}`; on = true; }
  else if (s.provider === "openai_compat" && s.base && s.model) { label = `AI · ${s.model}`; on = true; }
  else if (INFO?.server_provider) { label = `AI · ${INFO.server_model || INFO.server_provider}`; on = true; }
  pill.textContent = label; pill.classList.toggle("on", on);
}
function openSettings() {
  const s = loadLLM();
  $("#s-provider").value = s.provider || "anthropic";
  $("#s-key").value = s.key || ""; $("#s-base").value = s.base || ""; $("#s-okey").value = s.okey || "";
  $("#s-model").value = s.model || ""; $("#s-result").textContent = "";
  $("#s-server").textContent = INFO?.server_provider
    ? `This server also has its own model configured (${INFO.server_provider}${INFO.server_model ? " · " + INFO.server_model : ""}). It is used when you don't connect your own.` : "";
  syncProviderFields(); $("#settings").showModal();
}
const readSettingsForm = () => ({ provider: $("#s-provider").value, key: $("#s-key").value.trim(), base: $("#s-base").value.trim(), okey: $("#s-okey").value.trim(), model: $("#s-model").value.trim() });
function syncProviderFields() {
  const p = $("#s-provider").value;
  $$("#settings [data-for]").forEach(el => { el.style.display = el.dataset.for.split(" ").includes(p) ? "" : "none"; });
  $("#s-model").placeholder = p === "anthropic" ? (INFO?.default_anthropic_model || "claude-sonnet-5-5") : "qwen3:8b";
}
$("#open-settings").onclick = openSettings; $("#ai-pill").onclick = openSettings; $("#nav-ai").onclick = openSettings;
$("#s-provider").onchange = syncProviderFields;
$("#s-save").onclick = () => { saveLLM(readSettingsForm()); refreshPill(); $("#settings").close(); toast("AI settings saved in this browser"); };
$("#s-test").onclick = async () => {
  const prev = loadLLM(); saveLLM(readSettingsForm());
  const out = $("#s-result"); out.textContent = "Testing…";
  try { const r = await api("/api/llm/test", { method: "POST", body: llmPayload() }); out.textContent = `✓ Connected: ${r.provider}`; }
  catch (e) { out.textContent = `✗ ${e.message}`; }
  saveLLM(prev);
};

// sidebar collapse
const shell = $("#shell");
shell.classList.toggle("collapsed", lsGet("clipforge.collapsed", false));
$("#nav-collapse").onclick = () => { const c = !shell.classList.contains("collapsed"); shell.classList.toggle("collapsed", c); lsSet("clipforge.collapsed", c); };

// ============================================================== "create" ==
const LENGTHS = [
  { label: "Auto (15–60s)", min: 15, max: 60 },
  { label: "Under 30s", min: 10, max: 30 },
  { label: "30–60s", min: 30, max: 60 },
  { label: "60–90s", min: 60, max: 90 },
];
const RECIPES = {
  viral:   { label: "Viral clips", icon: "flame", mode: "analyze", style: "bold", fit: "blur", captions: true, cta: "Get clips in 1 click" },
  gaming:  { label: "Gaming highlights", icon: "game", mode: "analyze", style: "neon", fit: "blur", captions: true, len: 1, cta: "Find highlights",
             context: "Gameplay footage: action, clutch plays, chases, fails and funny moments" },
  podcast: { label: "Podcast clips", icon: "mic", mode: "analyze", style: "boxed", fit: "crop", captions: true, len: 2, cta: "Find best moments",
             context: "Podcast or interview: strong opinions, stories and quotable lines" },
  captions:{ label: "Captions only", icon: "cc", mode: "whole", style: "bold", fit: "blur", captions: true, cta: "Add captions" },
  reframe: { label: "Reframe only", icon: "crop", mode: "whole", style: "bold", fit: "crop", captions: false, cta: "Reframe video" },
};
const prefs = Object.assign({ tab: "link", recipe: "viral", len: 0, aspect: "9:16", auto: true, folder: "" }, lsGet("clipforge.create", {}));
const savePrefs = () => lsSet("clipforge.create", prefs);

function autorunBody() {
  const r = RECIPES[prefs.recipe] || RECIPES.viral, L = LENGTHS[prefs.len] || LENGTHS[0];
  const render = { ...(INFO?.render_defaults || {}), aspect: prefs.aspect, fit: r.fit, captions: r.captions, caption_style: r.style };
  if (!prefs.auto) return { mode: "none" };
  return { mode: r.mode, render, analyze: { min_len: L.min, max_len: L.max, count: 8, context: r.context || "", auto_render: true, render, llm: llmPayload() } };
}

function detectPlatform(url) {
  try {
    const h = new URL(/^https?:\/\//i.test(url) ? url : `https://${url}`).hostname.toLowerCase();
    const map = [["youtube.com", "youtube"], ["youtu.be", "youtube"], ["tiktok.com", "tiktok"], ["instagram.com", "instagram"], ["x.com", "x"], ["twitter.com", "x"],
      ["twitch.tv", "twitch"], ["facebook.com", "facebook"], ["fb.watch", "facebook"], ["vimeo.com", "vimeo"], ["drive.google.com", "drive"]];
    for (const [d, p] of map) if (h === d || h.endsWith("." + d)) return p;
    return h.includes(".") ? "web" : null;
  } catch { return null; }
}

function createCard() {
  const r = RECIPES[prefs.recipe];
  const folderOpts = `<option value="">No folder</option>${FOLDERS.map(f => `<option value="${f.id}" ${f.id === prefs.folder ? "selected" : ""}>${esc(f.name)}</option>`).join("")}<option value="__new">+ New folder…</option>`;
  return `
  <section class="create" aria-label="Start a project">
    <div class="ctabs" role="tablist">
      <button class="ctab" role="tab" data-tab="link" aria-selected="${prefs.tab === "link"}">${icon("link")} Paste link</button>
      <button class="ctab" role="tab" data-tab="upload" aria-selected="${prefs.tab === "upload"}">${icon("upload")} Upload file</button>
    </div>
    <div class="ccard ${prefs.tab === "upload" ? "first-off" : ""}">
      <form class="urlbox" id="link-form" ${prefs.tab !== "link" ? "hidden" : ""}>
        <span class="plat-slot" id="plat-slot">${icon("link")}</span>
        <input id="link" type="url" inputmode="url" autocomplete="off" aria-label="Video link"
          placeholder="Drop a YouTube, TikTok, Instagram or X link" />
        <button class="btn primary lg" id="go" type="submit">${prefs.auto ? esc(r.cta) : "Import video"}</button>
      </form>
      <div class="drop" id="drop" tabindex="0" role="button" aria-label="Upload a video file" ${prefs.tab !== "upload" ? "hidden" : ""}>
        <div class="ico">${icon("upload")}</div>
        <div class="big">Drop a video here or click to browse</div>
        <div class="muted" style="font-size:.85rem">MP4, MOV, MKV, WEBM · up to ${INFO?.max_upload_mb ? Math.round(INFO.max_upload_mb / 1024) + " GB" : "4 GB"}</div>
        <input type="file" id="file" accept="video/*" hidden />
        <div class="progress" id="up-prog" hidden><div style="width:0"></div></div>
        <div class="hint" id="up-txt"></div>
      </div>
      <div class="copts">
        <label class="select-chip">${icon("folder")}<select id="o-folder" aria-label="Save to folder">${folderOpts}</select></label>
        <label class="select-chip">${icon("crop")}<select id="o-aspect" aria-label="Format">${["9:16", "1:1", "4:5", "16:9"].map(a => `<option ${a === prefs.aspect ? "selected" : ""}>${a}</option>`).join("")}</select></label>
        <label class="select-chip" ${r.mode !== "analyze" ? "hidden" : ""} id="o-len-wrap">${icon("clock")}<select id="o-len" aria-label="Clip length">${LENGTHS.map((l, i) => `<option value="${i}" ${i === prefs.len ? "selected" : ""}>${l.label}</option>`).join("")}</select></label>
        <span class="sep"></span>
        <label class="switch"><input type="checkbox" id="o-auto" ${prefs.auto ? "checked" : ""} /><span class="track"></span> Auto-process</label>
      </div>
    </div>
    <div class="recipes" role="group" aria-label="What should ClipForge do?">
      ${Object.entries(RECIPES).map(([k, v]) => `<button class="chip" data-recipe="${k}" aria-pressed="${k === prefs.recipe}">${icon(v.icon)} ${v.label}</button>`).join("")}
    </div>
    <div class="works-with">Works with <span class="plats">${["youtube", "tiktok", "instagram", "x", "twitch", "facebook", "vimeo", "drive"].map(p => `<span title="${plat(p).name}">${platSvg(p, 18)}</span>`).join("")}</span> and most public video links</div>
  </section>`;
}

function bindCreate(rerender) {
  $$(".ctab").forEach(t => t.onclick = () => { prefs.tab = t.dataset.tab; savePrefs(); rerender(); });
  $$(".chip[data-recipe]").forEach(c => c.onclick = () => {
    prefs.recipe = c.dataset.recipe; const r = RECIPES[prefs.recipe];
    if (r.len != null) prefs.len = r.len; else if (r.mode === "analyze") prefs.len = 0;
    savePrefs(); rerender();
  });
  $("#o-aspect").onchange = e => { prefs.aspect = e.target.value; savePrefs(); };
  $("#o-len").onchange = e => { prefs.len = +e.target.value; savePrefs(); };
  $("#o-auto").onchange = e => { prefs.auto = e.target.checked; savePrefs(); $("#go").textContent = prefs.auto ? RECIPES[prefs.recipe].cta : "Import video"; };
  $("#o-folder").onchange = async e => {
    if (e.target.value === "__new") {
      const v = await folderForm("New folder");
      if (v) { const f = await api("/api/folders", { method: "POST", body: v }).catch(fail); await loadFolders(); if (f) prefs.folder = f.id; }
      savePrefs(); rerender(); return;
    }
    prefs.folder = e.target.value; savePrefs();
  };

  const link = $("#link");
  if (link) {
    if (prefs.tab === "link") setTimeout(() => link.focus());
    link.oninput = () => { const p = detectPlatform(link.value.trim()); $("#plat-slot").innerHTML = p && p !== "web" ? platSvg(p, 20) : icon("link"); };
    $("#link-form").onsubmit = async e => {
      e.preventDefault();
      const url = link.value.trim();
      if (!url) { link.focus(); return toast("Paste a video link first"); }
      const go = $("#go"); go.disabled = true; go.textContent = "Starting…";
      try {
        const p = await api("/api/projects/import", { method: "POST", body: { url, folder: prefs.folder || null, after: autorunBody() } });
        location.hash = `#/p/${p.id}`;
      } catch (err) { fail(err); go.disabled = false; go.textContent = prefs.auto ? RECIPES[prefs.recipe].cta : "Import video"; }
    };
    link.addEventListener("paste", () => setTimeout(() => link.oninput(), 0));
  }
  const drop = $("#drop"), file = $("#file");
  if (drop) {
    drop.onclick = () => file.click();
    drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); } };
    drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
    file.onchange = () => file.files[0] && upload(file.files[0]);
  }
}

function upload(f) {
  const bar = $("#up-prog"), txt = $("#up-txt"); bar.hidden = false;
  const fd = new FormData(); fd.append("file", f); if (prefs.folder) fd.append("folder", prefs.folder);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/projects");
  xhr.upload.onprogress = e => { if (e.lengthComputable) { const pc = (e.loaded / e.total) * 100; bar.firstElementChild.style.width = `${pc}%`; txt.textContent = `Uploading ${f.name} · ${pc.toFixed(0)}%`; } };
  xhr.upload.onload = () => { txt.textContent = "Reading video…"; bar.classList.add("indet"); };
  xhr.onload = async () => {
    bar.classList.remove("indet");
    if (xhr.status >= 200 && xhr.status < 300) {
      const p = JSON.parse(xhr.responseText);
      const body = autorunBody();
      if (body.mode !== "none") await api(`/api/projects/${p.id}/autorun`, { method: "POST", body }).catch(fail);
      location.hash = `#/p/${p.id}`;
    } else { bar.hidden = true; txt.textContent = ""; let m = xhr.statusText; try { m = JSON.parse(xhr.responseText).detail; } catch {} fail(new Error(`Upload failed: ${m}`)); }
  };
  xhr.onerror = () => { bar.hidden = true; txt.textContent = ""; fail(new Error("Upload failed: connection lost")); };
  xhr.send(fd);
}

// ======================================================= project cards ==
const busy = p => p.status === "downloading" || p.status === "processing" || (p.clips || []).some(c => ["rendering", "queued"].includes(c.render_state));
function statusTag(p) {
  if (p.status === "downloading") return `<span class="tag busy">${icon("download")} Importing ${Math.round((p.progress || 0) * 100)}%</span>`;
  if (p.status === "processing") return `<span class="tag busy">${icon("sparkle")} ${esc((p.stage || "Processing").split(" (")[0].slice(0, 26))}</span>`;
  if (p.status === "error") return `<span class="tag err">${icon("alert")} Failed</span>`;
  if (p.clips?.length) return `<span class="tag ok">${icon("scissors")} ${p.clips.length} clip${p.clips.length === 1 ? "" : "s"}</span>`;
  return "";
}
function projectCard(p) {
  const f = folderById(p.folder);
  const thumb = p.video ? `/media/${p.id}/thumb.jpg` : (p.import_meta?.thumbnail || "");
  const pct = p.status === "downloading" || p.status === "processing" ? Math.round((p.progress || 0) * 100) : null;
  const length = p.video?.duration || p.import_meta?.duration;
  return `
  <article class="pcard" draggable="true" data-id="${p.id}" tabindex="0" aria-label="${esc(p.name)}">
    <div class="thumb">
      <div class="ph">${icon("film")}</div>
      ${thumb ? `<img src="${esc(thumb)}" alt="" draggable="false" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()" />` : ""}
      <div class="shade"></div>
      <div class="tl"><span class="tag">${platSvg(p.platform || "upload", 13)} ${esc(plat(p.platform || "upload").name)}</span>${statusTag(p)}</div>
      ${length ? `<div class="br"><span class="tag">${dur(length)}</span></div>` : ""}
      ${pct != null ? `<div class="bar"><div style="width:${pct}%"></div></div>` : ""}
    </div>
    <div class="pbody">
      <div class="txt">
        <div class="ptitle" title="${esc(p.name)}">${esc(p.name)}</div>
        <div class="pmeta">${f ? `<span class="fdot" style="background:${f.color}"></span>${esc(f.name)} ·` : ""} ${ago(p.created)}</div>
      </div>
      <button class="icon-btn" data-more aria-label="Project actions">${icon("more")}</button>
    </div>
  </article>`;
}
function bindProjectCards(root, onChange) {
  root.onclick = e => {
    const card = e.target.closest(".pcard"); if (!card) return;
    const id = card.dataset.id;
    if (e.target.closest("[data-more]")) { e.stopPropagation(); projectMenu(e.target.closest("[data-more]"), id, onChange); return; }
    location.hash = `#/p/${id}`;
  };
  root.onkeydown = e => { const card = e.target.closest(".pcard"); if (card && e.key === "Enter" && e.target === card) location.hash = `#/p/${card.dataset.id}`; };
  root.ondragstart = e => { const c = e.target.closest(".pcard"); if (!c) return; e.dataTransfer.setData("text/clipforge-project", c.dataset.id); e.dataTransfer.effectAllowed = "move"; c.classList.add("dragging"); };
  root.ondragend = e => e.target.closest?.(".pcard")?.classList.remove("dragging");
}
async function projectMenu(anchor, id, onChange) {
  const p = await api(`/api/projects/${id}`).catch(fail); if (!p) return;
  const items = [
    { label: "Open", icon: "external", run: () => location.hash = `#/p/${id}` },
    { label: "Rename", icon: "edit", run: async () => { const n = await textPrompt("Rename project", "Name", p.name); if (n) { await api(`/api/projects/${id}`, { method: "PATCH", body: { name: n } }).catch(fail); onChange(); } } },
    { label: "Move to folder…", icon: "move", run: () => moveProject(p, onChange) },
  ];
  if (p.source_url) items.push({ label: "Open original link", icon: "link", run: () => window.open(p.source_url, "_blank", "noopener") });
  items.push("-", { label: "Delete project", icon: "trash", danger: true, run: async () => {
    if (await confirmBox("Delete project?", `“${p.name}” and all its clips will be removed from this computer.`)) {
      await api(`/api/projects/${id}`, { method: "DELETE" }).catch(fail); toast("Project deleted"); onChange();
    } } });
  showMenu(anchor, items);
}
async function moveProject(p, onChange) {
  const pick = await pickFolder(p.folder); if (!pick) return;
  if (pick.create) {
    const v = await folderForm("New folder"); if (!v) return;
    const nf = await api("/api/folders", { method: "POST", body: v }).catch(fail); if (!nf) return;
    await loadFolders(); pick.id = nf.id;
  }
  await api(`/api/projects/${p.id}`, { method: "PATCH", body: { folder: pick.id } }).catch(fail);
  const f = folderById(pick.id); toast(f ? `Moved to ${f.name}` : "Moved to Unsorted"); onChange();
}

// ================================================================= home ==
async function renderHome() {
  setCrumbs([{ label: "Home" }]);
  await loadFolders();
  const draw = () => {
    view.innerHTML = `
      <section class="hero">
        <h1>Long video in. <em>Viral shorts</em> out.</h1>
        <p class="muted">Paste a link or upload a file. ClipForge finds the best moments, reframes them for vertical and adds animated captions.</p>
      </section>
      ${createCard()}
      <p class="usage-note" id="usage-note" hidden></p>
      <div class="section-head"><h2>Recent projects</h2><a class="btn ghost sm" href="#/projects">View all ${icon("external")}</a></div>
      <div class="pgrid" id="recent">${Array(4).fill('<div class="skeleton" style="aspect-ratio:16/10"></div>').join("")}</div>`;
    bindCreate(draw);
    loadRecent(); usageNote();
  };
  const loadRecent = async () => {
    const grid = $("#recent"); if (!grid) return;
    const all = await api("/api/projects").catch(() => []);
    const list = all.slice(0, 8);
    grid.innerHTML = list.length ? list.map(projectCard).join("") : `<div class="empty"><div class="ico">${icon("film")}</div>No projects yet. Paste a link or upload a video to start.</div>`;
    bindProjectCards(grid, loadRecent);
    clearTimeout(pollTimer);
    if (list.some(busy) && location.hash.replace(/^#\/?$/, "") === "") pollTimer = setTimeout(loadRecent, 2000);
  };
  draw();
}

// ============================================================= library ==
async function renderLibrary(fid) {
  await loadFolders();
  const f = fid && fid !== "none" ? folderById(fid) : null;
  if (fid && fid !== "none" && !f) { location.hash = "#/projects"; return; }
  setCrumbs(f ? [{ label: "Projects", href: "#/projects" }, { label: f.name }] : fid === "none" ? [{ label: "Projects", href: "#/projects" }, { label: "Unsorted" }] : [{ label: "Projects" }]);
  let query = "";
  view.innerHTML = `
    <div class="lib-head">
      <div><h1 style="margin:0">${f ? esc(f.name) : fid === "none" ? "Unsorted" : "All projects"}</h1><div class="muted" id="lib-count" style="font-size:.88rem;margin-top:4px">&nbsp;</div></div>
      <div class="row" style="margin:0">
        <div class="search">${icon("search")}<input id="q" type="search" placeholder="Search projects" aria-label="Search projects" /></div>
        <a class="btn primary" href="#/">${icon("plus")} New project</a>
      </div>
    </div>
    <div class="folders" id="folders" role="list"></div>
    <div class="pgrid" id="lib">${Array(6).fill('<div class="skeleton" style="aspect-ratio:16/10"></div>').join("")}</div>`;

  const load = async () => {
    if (!$("#lib")) return;
    const [all] = await Promise.all([api("/api/projects").catch(() => []), loadFolders()]);
    const counts = { all: all.length, none: all.filter(p => !p.folder || !folderById(p.folder)).length };
    all.forEach(p => { if (p.folder) counts[p.folder] = (counts[p.folder] || 0) + 1; });
    const tile = (id, name, color, ic, count, href, manage) => `
      <a class="ftile ${(fid || "") === id ? "active" : ""}" href="${href}" data-drop="${id}" role="listitem">
        <span class="fic" style="background:${color}22;color:${color}">${icon(ic)}</span>
        <span><div class="fname">${esc(name)}</div><div class="fcount">${count} project${count === 1 ? "" : "s"}</div></span>
        ${manage ? `<button class="icon-btn" data-fmore="${id}" aria-label="Folder actions">${icon("more")}</button>` : ""}
      </a>`;
    $("#folders").innerHTML =
      tile("", "All projects", "#a1a1aa", "film", counts.all, "#/projects", false) +
      tile("none", "Unsorted", "#a1a1aa", "inbox", counts.none, "#/projects/none", false) +
      FOLDERS.map(x => tile(x.id, x.name, x.color, "folder", counts[x.id] || 0, `#/projects/${x.id}`, true)).join("") +
      `<button class="ftile add" id="new-folder">${icon("folderPlus")} New folder</button>`;

    let list = fid === "none" ? all.filter(p => !p.folder || !folderById(p.folder)) : fid ? all.filter(p => p.folder === fid) : all;
    if (query) list = list.filter(p => p.name.toLowerCase().includes(query));
    $("#lib-count").textContent = `${list.length} project${list.length === 1 ? "" : "s"}${!fid ? ` · ${FOLDERS.length} folder${FOLDERS.length === 1 ? "" : "s"}` : ""} · drag a project onto a folder to move it`;
    const lib = $("#lib");
    lib.innerHTML = list.length ? list.map(projectCard).join("")
      : `<div class="empty"><div class="ico">${icon(query ? "search" : "folder")}</div>${query ? "No projects match your search." : f ? "This folder is empty. Drag projects here or pick it when you create a project." : "No projects here yet."}</div>`;
    bindProjectCards(lib, load);
    clearTimeout(pollTimer);
    if (list.some(busy)) pollTimer = setTimeout(load, 2000);
  };

  const folders = $("#folders");
  folders.onclick = async e => {
    if (e.target.closest("#new-folder")) {
      const v = await folderForm("New folder"); if (!v) return;
      await api("/api/folders", { method: "POST", body: v }).catch(fail); toast(`Folder “${v.name}” created`); load(); return;
    }
    const more = e.target.closest("[data-fmore]"); if (!more) return;
    e.preventDefault(); e.stopPropagation();
    const folder = folderById(more.dataset.fmore);
    showMenu(more, [
      { label: "Rename or recolor", icon: "edit", run: async () => { const v = await folderForm("Edit folder", folder); if (v) { await api(`/api/folders/${folder.id}`, { method: "PATCH", body: v }).catch(fail); load(); if (fid === folder.id) setCrumbs([{ label: "Projects", href: "#/projects" }, { label: v.name }]); } } },
      "-",
      { label: "Delete folder", icon: "trash", danger: true, run: async () => {
        if (await confirmBox("Delete folder?", `“${folder.name}” will be removed. Its projects are kept and moved to Unsorted.`)) {
          await api(`/api/folders/${folder.id}`, { method: "DELETE" }).catch(fail); toast("Folder deleted");
          if (fid === folder.id) location.hash = "#/projects"; else load();
        } } },
    ]);
  };
  folders.ondragover = e => { const t = e.target.closest("[data-drop]"); if (!t || t.dataset.drop === "" || !e.dataTransfer.types.includes("text/clipforge-project")) return; e.preventDefault(); $$(".ftile", folders).forEach(x => x.classList.toggle("drop-over", x === t)); };
  folders.ondragleave = e => { if (!folders.contains(e.relatedTarget)) $$(".ftile", folders).forEach(x => x.classList.remove("drop-over")); };
  folders.ondrop = async e => {
    const t = e.target.closest("[data-drop]"); $$(".ftile", folders).forEach(x => x.classList.remove("drop-over"));
    const pid = e.dataTransfer.getData("text/clipforge-project"); if (!t || !pid) return;
    e.preventDefault();
    const target = t.dataset.drop === "none" ? "" : t.dataset.drop;
    if (t.dataset.drop === "" ) return; // "All" is not a destination
    await api(`/api/projects/${pid}`, { method: "PATCH", body: { folder: target } }).catch(fail);
    const nf = folderById(target); toast(nf ? `Moved to ${nf.name}` : "Moved to Unsorted"); load();
  };
  $("#q").oninput = e => { query = e.target.value.trim().toLowerCase(); load(); };
  load();
}

// ============================================================= project ==
const AN_LENGTHS = LENGTHS;
let lenChoice = 0;
let current = null;

async function renderProject(pid) {
  const p = await api(`/api/projects/${pid}`);
  await Promise.all([loadFolders(), loadPosted(pid)]);
  current = p;
  const f = folderById(p.folder);
  setCrumbs([{ label: "Projects", href: "#/projects" }, ...(f ? [{ label: f.name, href: `#/projects/${f.id}` }] : []), { label: p.name }]);

  if (!p.video) return renderPending(p);

  const pl = plat(p.platform || "upload");
  view.innerHTML = `
    <div class="proj-top">
      <div style="min-width:0">
        <h1>${esc(p.name)}</h1>
        <div class="meta-line">
          <span class="tag" style="background:var(--panel2)">${platSvg(p.platform || "upload", 13)} ${esc(pl.name)}</span>
          <span>${dur(p.video.duration)} · ${p.video.width}×${p.video.height} · ${p.video.fps} fps${p.video.has_audio ? "" : " · no audio"}</span>
          ${p.source_url ? `<a href="${esc(p.source_url)}" target="_blank" rel="noopener">${icon("external")} Original</a>` : ""}
        </div>
      </div>
      <div class="row" style="margin:0">
        <button class="btn ghost sm" id="move-proj">${f ? `<span class="fdot" style="background:${f.color}"></span>${esc(f.name)}` : `${icon("folder")} Add to folder`}</button>
        <button class="btn ghost sm" id="rename-proj">${icon("edit")} Rename</button>
        <button class="icon-btn" id="del-proj" aria-label="Delete project" title="Delete project">${icon("trash")}</button>
      </div>
    </div>
    <div class="project-head">
      <div>
        <video id="player" class="player" src="/media/${p.id}/${p.source}" controls preload="metadata"></video>
        <div class="heat" id="heat" title="Excitement over time (click to seek)"><canvas id="heat-c"></canvas><div class="head" id="heat-head"></div></div>
        <div class="hint">Heat bar = audio excitement. Highlighted ranges = clips.</div>
      </div>
      <div class="panel">
        <h3>${icon("sparkle")} Find viral moments</h3>
        <label>Clip length</label>
        <div class="presets" id="presets">${AN_LENGTHS.map((l, i) => `<button class="btn sm ghost ${i === lenChoice ? "active" : ""}" data-i="${i}">${l.label}</button>`).join("")}</div>
        <div class="row">
          <label class="grow">Number of clips<input id="a-count" type="number" min="1" max="30" value="8" /></label>
          <label class="grow">Format
            <select id="a-aspect">${["9:16", "1:1", "4:5", "16:9"].map(a => `<option ${a === prefs.aspect ? "selected" : ""}>${a}</option>`).join("")}</select></label>
        </div>
        <label>What is this video? (helps the AI)
          <textarea id="a-context" rows="2" placeholder="e.g. GTA 6 gameplay stream, funny police chases and fails"></textarea></label>
        <label class="check"><input id="a-captions" type="checkbox" checked /> Animated captions</label>
        <label class="check"><input id="a-auto" type="checkbox" checked /> Render clips automatically</label>
        <div class="row end"><button class="btn primary" id="analyze">${p.clips.length ? "Re-analyze" : "Get clips"}</button></div>
        <div id="status" aria-live="polite"></div>
        <hr style="border:0;border-top:1px solid var(--line);margin:16px 0">
        <h3>${icon("cc")} Captions or resize only</h3>
        <p class="hint">Make one clip from the whole video, or from a range you pick in the player, then caption and reformat it.</p>
        <div class="row">
          <button class="btn ghost sm" id="whole">Use whole video</button>
          <button class="btn ghost sm" id="mark-in">Mark start</button>
          <button class="btn ghost sm" id="mark-out">Mark end + add</button>
        </div>
      </div>
    </div>
    <div class="section-head"><h2>Clips</h2><span class="muted" id="note" style="font-size:.85rem"></span></div>
    <div class="clip-grid" id="clips"></div>`;

  $("#del-proj").onclick = async () => { if (await confirmBox("Delete project?", "This removes the video and all its clips from this computer.")) { await api(`/api/projects/${p.id}`, { method: "DELETE" }); location.hash = "#/projects"; } };
  $("#rename-proj").onclick = async () => { const n = await textPrompt("Rename project", "Name", current.name); if (n) { await api(`/api/projects/${p.id}`, { method: "PATCH", body: { name: n } }).catch(fail); route(); } };
  $("#move-proj").onclick = () => moveProject(current, route);
  $("#presets").onclick = e => { const b = e.target.closest("button"); if (!b) return; lenChoice = +b.dataset.i; $$("#presets button").forEach(x => x.classList.toggle("active", x === b)); };
  $("#analyze").onclick = () => startAnalyze(p.id);

  const player = $("#player");
  let markIn = null;
  $("#mark-in").onclick = () => { markIn = player.currentTime; toast(`Start marked at ${fmt(markIn)}`); };
  $("#mark-out").onclick = async () => {
    if (markIn === null) return toast("Mark a start first");
    const [s, e] = [Math.min(markIn, player.currentTime), Math.max(markIn, player.currentTime)];
    try { const c = await api(`/api/projects/${p.id}/clips`, { method: "POST", body: { start: s, end: e, title: "Manual clip" } }); markIn = null; await refresh(); openEditor(c.id); }
    catch (err) { fail(err); }
  };
  $("#whole").onclick = async () => {
    const c = await api(`/api/projects/${p.id}/clips`, { method: "POST", body: { start: 0, end: p.video.duration, title: p.name } }).catch(fail);
    if (c) { await refresh(); openEditor(c.id); }
  };
  player.ontimeupdate = () => { $("#heat-head").style.left = `${(player.currentTime / p.video.duration) * 100}%`; };
  $("#heat").onclick = e => { const r = e.currentTarget.getBoundingClientRect(); player.currentTime = ((e.clientX - r.left) / r.width) * p.video.duration; };

  await drawHeat(p);
  paint(p);
  schedulePoll(p);
}

function renderPending(p) {
  const pl = plat(p.platform || "web");
  const meta = p.import_meta || {};
  if (p.status === "error") {
    view.innerHTML = `
      <div class="panel big-state">
        <div class="ico" style="color:var(--bad)">${icon("alert")}</div>
        <h2>We couldn't import this video</h2>
        <p class="muted">${esc(p.message || "Unknown error")}</p>
        ${p.source_url ? `<p class="hint" style="word-break:break-all">${esc(p.source_url)}</p>` : ""}
        <div class="row" style="justify-content:center;margin-top:18px">
          ${p.source_url ? `<button class="btn primary" id="retry">${icon("refresh")} Try again</button>` : ""}
          <a class="btn ghost" href="#/">Upload instead</a>
          <button class="btn ghost danger" id="del">${icon("trash")} Delete</button>
        </div>
      </div>`;
    $("#retry")?.addEventListener("click", async () => { await api(`/api/projects/${p.id}/retry-import`, { method: "POST", body: autorunBody() }).catch(fail); route(); });
    $("#del").onclick = async () => { await api(`/api/projects/${p.id}`, { method: "DELETE" }).catch(fail); location.hash = "#/projects"; };
    return;
  }
  const pct = Math.round((p.progress || 0) * 100);
  view.innerHTML = `
    <div class="panel big-state" aria-live="polite">
      ${meta.thumbnail ? `<img class="prev" src="${esc(meta.thumbnail)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()" />` : `<div class="ico" style="background:${pl.bg}">${platSvg(p.platform, 28)}</div>`}
      <h2>${esc(p.name)}</h2>
      <p class="muted">${meta.uploader ? `${esc(meta.uploader)} · ` : ""}${meta.duration ? dur(meta.duration) + " · " : ""}${esc(pl.name)}</p>
      <div class="progress ${pct ? "" : "indet"}"><div style="width:${pct}%"></div></div>
      <p class="hint" style="margin-top:10px">${esc(p.stage || "Starting")}${pct ? ` · ${pct}%` : "…"}</p>
      <p class="hint">You can leave this page. The import keeps running and the project will show up in your library.</p>
    </div>`;
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    if (!location.hash.startsWith(`#/p/${p.id}`)) return;
    const np = await api(`/api/projects/${p.id}`).catch(() => null);
    if (!np) return;
    if (np.video) route(); else renderPending(np);
  }, 1200);
}

async function drawHeat(p) {
  const { values } = await api(`/api/projects/${p.id}/signals`).catch(() => ({ values: [] }));
  const c = $("#heat-c"); if (!c) return;
  const w = c.clientWidth * devicePixelRatio, h = c.clientHeight * devicePixelRatio;
  c.width = w; c.height = h;
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  if (!values.length) return;
  const max = Math.max(...values, 1), bw = w / values.length;
  values.forEach((v, i) => {
    const t = Math.max(0, v) / max, bh = Math.max(2, t * h);
    ctx.fillStyle = `hsla(${75 - t * 60}, 90%, ${42 + t * 18}%, ${0.3 + t * 0.7})`;
    ctx.fillRect(i * bw, h - bh, Math.ceil(bw), bh);
  });
}

function paint(p) {
  current = p;
  const status = $("#status"); if (!status) return;
  if (p.status === "processing") {
    status.innerHTML = `<div class="hint" style="margin-top:8px">${esc(p.stage)}…</div><div class="progress"><div style="width:${(p.progress * 100).toFixed(0)}%"></div></div>`;
    $("#analyze").disabled = true;
  } else {
    $("#analyze").disabled = false;
    status.innerHTML = p.status === "error" ? `<p class="hint" style="color:var(--bad)">${esc(p.message)}</p>` : "";
  }
  $("#note").textContent = p.analysis_note || "";

  const heat = $("#heat");
  heat.querySelectorAll(".mark").forEach(m => m.remove());
  p.clips.forEach(c => {
    const m = document.createElement("div"); m.className = "mark";
    m.style.left = `${(c.start / p.video.duration) * 100}%`; m.style.width = `${((c.end - c.start) / p.video.duration) * 100}%`;
    m.title = c.title; heat.appendChild(m);
  });

  const grid = $("#clips");
  if (!p.clips.length) { grid.innerHTML = `<div class="empty"><div class="ico">${icon(p.status === "processing" ? "sparkle" : "scissors")}</div>${p.status === "processing" ? "Working on it… clips appear here as they're found." : "No clips yet. Click <b>Get clips</b>."}</div>`; return; }
  const existing = new Map([...grid.querySelectorAll(".clip-card")].map(el => [el.dataset.id, el]));
  const frag = document.createDocumentFragment();
  p.clips.forEach(c => {
    const key = JSON.stringify([c.render_state, c.render?.at, c.title, c.score, c.hashtags, c.start, c.end, c.render_error, POSTED[c.id]]);
    let el = existing.get(c.id);
    if (!el || el.dataset.key !== key) { el = clipCard(p, c); el.dataset.key = key; }
    frag.appendChild(el);
  });
  grid.replaceChildren(frag);
}

function clipCard(p, c) {
  const el = document.createElement("div");
  el.className = "card clip-card"; el.dataset.id = c.id;
  const aspect = c.render?.settings?.aspect || "9:16";
  const cls = { "1:1": "sq", "4:5": "f45", "16:9": "wide" }[aspect] || "";
  const sc = c.score >= 80 ? "hot" : c.score >= 60 ? "mid" : "low";
  let media;
  if (c.render_state === "done" && c.render) {
    media = `<video src="/media/${p.id}/clips/${c.render.file}?v=${c.render.at}" poster="/media/${p.id}/clips/${c.render.thumb}?v=${c.render.at}" controls preload="none" playsinline></video>`;
  } else if (c.render_state === "rendering" || c.render_state === "queued") {
    media = `<div class="state"><div class="spinner"></div>${c.render_state === "queued" ? "Queued" : "Rendering…"}</div>`;
  } else if (c.render_state === "error") {
    media = `<div class="state" style="color:var(--bad)">Render failed<br><small>${esc((c.render_error || "").slice(0, 160))}</small></div>`;
  } else {
    media = `<div class="state">Not rendered yet</div>`;
  }
  el.innerHTML = `
    <div class="media ${cls}">${media}
      ${c.source !== "manual" ? `<span class="score ${sc}" title="Virality score">${c.score}</span>` : ""}
      <span class="tag src">${c.source === "ai" ? "AI" : c.source === "signals" ? "signals" : "manual"}</span>
    </div>
    <div class="body">
      <h3>${esc(c.title)}</h3>
      <div class="muted" style="font-size:.8rem">${fmt(c.start)} → ${fmt(c.end)} · ${(c.end - c.start).toFixed(0)}s</div>
      ${c.reason ? `<div class="reason">${esc(c.reason)}</div>` : ""}
      ${c.hashtags?.length ? `<div class="tags">${esc(c.hashtags.join(" "))}</div>` : ""}
      ${postedBadges(c.id)}
      <div class="row">
        ${c.render_state === "done" ? `<button class="btn sm accent" data-act="post">${icon("send")} Post</button>` : ""}
        <button class="btn sm" data-act="edit">${icon("edit")} Edit</button>
        ${c.render_state === "done" ? `<a class="btn sm" href="/media/${p.id}/clips/${c.render.file}?download=1&name=${slug(c.title)}.mp4">${icon("download")} Download</a>` : `<button class="btn sm" data-act="render">Render</button>`}
        <button class="icon-btn" data-act="copy" title="Copy title + hashtags" aria-label="Copy title and hashtags">${icon("copy")}</button>
        <button class="icon-btn" data-act="del" title="Delete clip" aria-label="Delete clip">${icon("trash")}</button>
      </div>
    </div>`;
  el.onclick = async e => {
    const act = e.target.closest("[data-act]")?.dataset.act; if (!act) return;
    if (act === "edit") openEditor(c.id);
    if (act === "post") openPublish(p, c);
    if (act === "render") { await api(`/api/projects/${p.id}/clips/${c.id}/render`, { method: "POST", body: defaultRender() }).catch(fail); refresh(); }
    if (act === "copy") { try { await navigator.clipboard.writeText(`${c.title}\n\n${(c.hashtags || []).join(" ")}`); toast("Copied title + hashtags"); } catch { toast("Clipboard blocked by the browser", 3000, true); } }
    if (act === "del" && await confirmBox("Delete clip?", `“${c.title}” will be removed.`)) { await api(`/api/projects/${p.id}/clips/${c.id}`, { method: "DELETE" }).catch(fail); refresh(); }
  };
  return el;
}

function defaultRender() {
  return { ...(INFO?.render_defaults || {}), aspect: $("#a-aspect")?.value || "9:16", captions: $("#a-captions")?.checked ?? true };
}

async function startAnalyze(pid) {
  const l = AN_LENGTHS[lenChoice];
  if (!llmReady() && !INFO?.server_provider && !lsGet("clipforge.warned", false)) {
    lsSet("clipforge.warned", true);
    toast("No AI connected: using audio/scene signals. Connect Claude for smarter picks.", 5000);
  }
  try {
    await api(`/api/projects/${pid}/analyze`, { method: "POST", body: {
      min_len: l.min, max_len: l.max, count: +$("#a-count").value || 8, context: $("#a-context").value,
      auto_render: $("#a-auto").checked, render: defaultRender(), llm: llmPayload() } });
    refresh();
  } catch (e) { fail(e); }
}

async function refresh() {
  if (!current || !$("#clips")) return;
  const p = await api(`/api/projects/${current.id}`).catch(() => null); if (!p) return;
  const wasProcessing = current.status === "processing";
  paint(p);
  if (wasProcessing && p.status !== "processing") drawHeat(p);
  schedulePoll(p);
}
function schedulePoll(p) {
  clearTimeout(pollTimer);
  if (busy(p) && location.hash.startsWith("#/p/")) pollTimer = setTimeout(refresh, 1500);
}

// --------------------------------------------------------------- editor --
let edClip = null;
function openEditor(cid) {
  const p = current, c = p.clips.find(x => x.id === cid); if (!c) return;
  edClip = c;
  const s = { ...(INFO?.render_defaults || {}), ...(c.render?.settings || defaultRender()) };
  $("#e-src").src = `/media/${p.id}/${p.source}#t=${c.start}`;
  $("#e-title").textContent = c.title;
  $("#e-start").value = c.start; $("#e-end").value = c.end; $("#e-start").max = $("#e-end").max = p.video.duration;
  $("#e-name").value = c.title; $("#e-hook").value = c.hook || ""; $("#e-tags").value = (c.hashtags || []).join(" ");
  $("#e-aspect").value = s.aspect; $("#e-fit").value = s.fit; $("#e-cropx").value = s.crop_x;
  $("#e-captions").checked = s.captions; $("#e-style").value = s.caption_style; $("#e-pos").value = s.caption_position;
  $("#e-showhook").checked = s.show_hook;
  $("#e-out").innerHTML = c.render_state === "done" ? `<div class="hint">Current render</div><video controls playsinline src="/media/${p.id}/clips/${c.render.file}?v=${c.render.at}"></video>` : "";
  updateLen(); updateCrop();
  $("#editor").showModal();
}
function updateLen() { $("#e-len").textContent = `${(($("#e-end").value - $("#e-start").value) || 0).toFixed(1)}s`; }
function updateCrop() {
  const box = $("#e-crop");
  const [W, H] = $("#e-aspect").value.split(":").map(Number);
  const vw = current?.video?.width, vh = current?.video?.height;
  const fit = $("#e-fit").value;
  $("#e-cropx-wrap").style.display = fit === "crop" ? "" : "none";
  if (fit !== "crop" || !vw || W / H >= vw / vh) { box.style.display = "none"; return; }
  const frac = (W / H) / (vw / vh), x = +$("#e-cropx").value;
  box.style.display = "block"; box.style.width = `${frac * 100}%`; box.style.left = `${(1 - frac) * x * 100}%`;
}
["#e-start", "#e-end"].forEach(s => $(s).oninput = updateLen);
["#e-aspect", "#e-fit", "#e-cropx"].forEach(s => $(s).oninput = updateCrop);
$("#e-close").onclick = () => { $("#e-src").pause(); $("#editor").close(); };
$("#editor").addEventListener("close", () => $("#e-src").pause());
$("#e-set-in").onclick = () => { $("#e-start").value = $("#e-src").currentTime.toFixed(2); updateLen(); };
$("#e-set-out").onclick = () => { $("#e-end").value = $("#e-src").currentTime.toFixed(2); updateLen(); };
$("#e-play").onclick = () => {
  const v = $("#e-src"), s = +$("#e-start").value, e = +$("#e-end").value;
  v.muted = false; v.currentTime = s; v.play();
  v.ontimeupdate = () => { if (v.currentTime >= e) { v.pause(); v.ontimeupdate = null; } };
};
$("#e-render").onclick = async () => {
  const p = current, c = edClip;
  try {
    await api(`/api/projects/${p.id}/clips/${c.id}`, { method: "PATCH", body: {
      start: +$("#e-start").value, end: +$("#e-end").value, title: $("#e-name").value, hook: $("#e-hook").value,
      hashtags: $("#e-tags").value.split(/\s+/).filter(Boolean).map(t => t.startsWith("#") ? t : `#${t}`) } });
    await api(`/api/projects/${p.id}/clips/${c.id}/render`, { method: "POST", body: {
      aspect: $("#e-aspect").value, fit: $("#e-fit").value, crop_x: +$("#e-cropx").value,
      captions: $("#e-captions").checked, caption_style: $("#e-style").value,
      caption_position: +$("#e-pos").value, show_hook: $("#e-showhook").checked } });
    $("#editor").close(); toast("Rendering…"); refresh();
  } catch (e) { fail(e); }
};

// =========================================================== analytics ==
let anDays = 30;
async function renderAnalytics() {
  setCrumbs([{ label: "Analytics" }]);
  view.innerHTML = `<div class="lib-head"><div><h1 style="margin:0">Analytics</h1><div class="muted" style="font-size:.88rem;margin-top:4px">Your clipping output and connected accounts</div></div></div>
    <div class="kpis">${Array(6).fill('<div class="skeleton" style="height:104px"></div>').join("")}</div>`;
  await loadFolders();
  const a = await api(`/api/analytics?days=${anDays}`);
  const t = a.totals;
  const sc = s => s == null ? "—" : s;
  const daily = a.daily, max = Math.max(1, ...daily.map(d => Math.max(d.imported, d.rendered)));
  const nice = Math.max(2, Math.ceil(max / (max > 10 ? 5 : 1)) * (max > 10 ? 5 : 1));
  const dlabel = d => new Date(d + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const bucketsMax = Math.max(1, ...a.score_buckets);
  const platEntries = Object.entries(a.platforms), platMax = Math.max(1, ...platEntries.map(e => e[1]));
  const connected = a.social.filter(s => s.connected);

  view.innerHTML = `
    <div class="lib-head">
      <div><h1 style="margin:0">Analytics</h1><div class="muted" style="font-size:.88rem;margin-top:4px">Your clipping output and connected accounts</div></div>
      <div class="range" role="group" aria-label="Time range">${[7, 30, 90].map(d => `<button data-d="${d}" aria-pressed="${d === anDays}">${d} days</button>`).join("")}</div>
    </div>

    <div class="kpis">
      ${kpi("film", "Projects", t.projects, `${num(t.source_minutes)} min of source`)}
      ${kpi("scissors", "Clips found", t.clips, `${t.rendered} rendered`)}
      ${kpi("clock", "Minutes of shorts", t.clip_minutes, "rendered output")}
      ${kpi("star", "Avg virality score", sc(t.avg_score), "AI + signal picks")}
      ${kpi("flame", "Viral-grade clips", t.viral_clips, "score 80 or higher")}
      ${kpi("plug", "Followers (connected)", connected.length ? num(connected.reduce((s, c) => s + (c.stats?.followers || 0), 0)) : "—", connected.length ? `${connected.length} account${connected.length > 1 ? "s" : ""}` : "no accounts connected")}
    </div>

    <div class="agrid">
      <section class="panel span-8" aria-labelledby="ch-act">
        <div class="chart-head"><h3 id="ch-act">Activity</h3>
          <div class="legend"><span><i style="background:var(--s1)"></i>Videos imported</span><span><i style="background:var(--s2)"></i>Clips rendered</span></div></div>
        <div class="cols" role="img" aria-label="Videos imported and clips rendered per day over the last ${anDays} days">
          ${[1, 0.5].map(f => `<div class="grid-l" style="bottom:${f * 100}%"><span>${Math.round(nice * f)}</span></div>`).join("")}
          ${daily.map(d => `<div class="col" data-tip="<b>${dlabel(d.day)}</b><br><i style='background:var(--s1)'></i>Imported ${d.imported}<br><i style='background:var(--s2)'></i>Rendered ${d.rendered}">
              <div class="b" style="height:${(d.imported / nice) * 100}%;background:var(--s1)"></div>
              <div class="b" style="height:${(d.rendered / nice) * 100}%;background:var(--s2)"></div></div>`).join("")}
        </div>
        <div class="xlabels"><span>${dlabel(daily[0].day)}</span><span>${dlabel(daily[Math.floor(daily.length / 2)].day)}</span><span>Today</span></div>
      </section>

      <section class="panel span-4" aria-labelledby="ch-plat">
        <div class="chart-head"><h3 id="ch-plat">Where your videos come from</h3></div>
        ${platEntries.length ? `<div class="hbars">${platEntries.map(([k, v]) => `
          <div class="hbar" data-tip="${esc(plat(k).name)}: ${v} project${v === 1 ? "" : "s"}"><span class="nm">${platSvg(k, 16)} ${esc(plat(k).name)}</span>
          <div class="tr"><div class="fl" style="width:${(v / platMax) * 100}%"></div></div><span class="val">${v}</span></div>`).join("")}</div>`
          : `<p class="hint">Import a video to see sources.</p>`}
      </section>

      <section class="panel span-6" aria-labelledby="ch-score">
        <div class="chart-head"><h3 id="ch-score">Virality score distribution</h3><span class="hint">${a.score_buckets.reduce((x, y) => x + y, 0)} scored clips</span></div>
        <div class="cols" style="height:150px" role="img" aria-label="Number of clips in each virality score band">
          ${a.score_buckets.map((v, i) => `<div class="col" data-tip="Score ${i * 10}–${i === 9 ? 100 : i * 10 + 9}: <b>${v}</b> clip${v === 1 ? "" : "s"}">
            <div class="b" style="max-width:none;height:${(v / bucketsMax) * 100}%;background:var(--s1)"></div></div>`).join("")}
        </div>
        <div class="xlabels even">${a.score_buckets.map((_, i) => `<span>${i * 10}</span>`).join("")}</div>
      </section>

      <section class="panel span-6" aria-labelledby="ch-top">
        <div class="chart-head"><h3 id="ch-top">Top clips</h3></div>
        ${a.top_clips.length ? `<div class="toplist">${a.top_clips.map((c, i) => `
          <a class="toprow" href="#/p/${c.project_id}">
            <span class="rk">${i + 1}</span>
            ${c.thumb ? `<img class="th" src="/media/${c.project_id}/clips/${c.thumb}" alt="" loading="lazy" />` : `<span class="th" style="display:grid;place-items:center;color:var(--dim)">${icon("film")}</span>`}
            <span style="min-width:0"><div class="t1">${esc(c.title)}</div><div class="t2">${esc(c.project)} · ${c.length}s</div></span>
            <span class="score ${c.score >= 80 ? "hot" : c.score >= 60 ? "mid" : "low"}" style="position:static">${c.source === "manual" ? "—" : c.score}</span>
          </a>`).join("")}</div>` : `<p class="hint">No clips yet.</p>`}
      </section>

      <section class="panel span-6" aria-labelledby="ch-tags">
        <div class="chart-head"><h3 id="ch-tags">Top hashtags</h3></div>
        ${a.top_hashtags.length ? `<div class="htags">${a.top_hashtags.map(([tg, n]) => `<span>${esc(tg)}<b>${n}</b></span>`).join("")}</div>` : `<p class="hint">Hashtags appear once the AI writes them for your clips.</p>`}
      </section>

      <section class="panel span-6" aria-labelledby="ch-fold">
        <div class="chart-head"><h3 id="ch-fold">Projects by folder</h3><a class="btn ghost sm" href="#/projects">Manage</a></div>
        ${a.folders.length ? `<div class="hbars">${a.folders.map(f => { const fm = Math.max(1, ...a.folders.map(x => x.projects)); return `
          <div class="hbar" data-tip="${esc(f.name)}: ${f.projects}"><span class="nm"><span class="fdot" style="background:${f.color}"></span>${esc(f.name)}</span>
          <div class="tr"><div class="fl" style="width:${(f.projects / fm) * 100}%"></div></div><span class="val">${f.projects}</span></div>`; }).join("")}</div>` : `<p class="hint">No projects yet.</p>`}
      </section>

      <section class="span-12" aria-labelledby="ch-soc">
        <div class="section-head" style="margin-top:12px"><h2 id="ch-soc">Social accounts</h2><a class="btn ghost sm" href="#/connections">${icon("plug")} Manage connections</a></div>
        ${connected.length ? `<div class="soc-grid">${connected.map(socialStatCard).join("")}</div>` :
          `<div class="empty"><div class="ico">${icon("plug")}</div>Connect YouTube, TikTok, Instagram or X to track followers and views next to your clipping output.<div style="margin-top:14px"><a class="btn primary" href="#/connections">Connect an account</a></div></div>`}
      </section>
    </div>`;
  $$(".range button").forEach(b => b.onclick = () => { anDays = +b.dataset.d; renderAnalytics(); });
  bindTips(view);
}
const kpi = (ic, k, v, s) => `<div class="kpi"><div class="k">${icon(ic)}${esc(k)}</div><div class="v">${typeof v === "number" ? num(v) : esc(v)}</div><div class="s">${esc(s)}</div></div>`;

function spark(history) {
  const pts = (history || []).map(h => h.followers || 0);
  if (pts.length < 2) return `<p class="hint" style="margin:0">Follower trend appears after a few days of data.</p>`;
  const mn = Math.min(...pts), mx = Math.max(...pts), rng = mx - mn || 1;
  const d = pts.map((v, i) => `${(i / (pts.length - 1)) * 100},${28 - ((v - mn) / rng) * 26}`).join(" ");
  const delta = pts.at(-1) - pts[0];
  return `<div class="hint" style="margin:0 0 4px">Followers over ${pts.length} days: <b style="color:var(--text)">${delta >= 0 ? "+" : ""}${num(delta)}</b></div>
    <svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none" role="img" aria-label="Follower trend"><polyline points="${d}"/></svg>`;
}
function socialStatCard(s) {
  const st = s.stats || {};
  const cells = [["followers", "Followers"], ["views", "Views"], ["likes", "Likes"], ["posts", "Posts"]].filter(([k]) => st[k] != null).slice(0, 3);
  return `
    <div class="soc">
      <div class="soc-top"><span class="bico" style="background:${plat(s.id).bg}">${platSvg(s.id, 22)}</span>
        <div style="min-width:0"><div class="nm">${esc(s.profile?.name || s.name)}</div><div class="status on">${esc(s.profile?.handle || s.name)}</div></div></div>
      <div class="sstats">${cells.map(([k, l]) => `<div><b>${num(st[k])}</b><span>${l}</span></div>`).join("")}</div>
      ${spark(s.history)}
    </div>`;
}

// ========================================================= connections ==
const SOCIAL_COPY = {
  youtube: "Post clips as Shorts and track subscribers and views.",
  tiktok: "Post clips to TikTok and track followers and likes.",
  instagram: "Post clips as Reels (Business or Creator accounts) and track followers.",
  x: "Post clips with your caption and track followers.",
};
// Flip to true to turn the social accounts page back on.
const SOCIAL_ENABLED = false;

function renderComingSoon() {
  setCrumbs([{ label: "Social accounts" }]);
  view.innerHTML = `
    <div class="panel big-state">
      <div class="ico" style="color:var(--accent)">${icon("plug")}</div>
      <h2>Coming soon</h2>
      <p class="muted">Connecting YouTube, TikTok, Instagram and X is on its way.</p>
      <div class="works-with" style="margin-top:14px"><span class="plats">${["youtube", "tiktok", "instagram", "x"].map(p => `<span title="${plat(p).name}">${platSvg(p, 22)}</span>`).join("")}</span></div>
      <div class="row" style="justify-content:center;margin-top:18px"><a class="btn primary" href="#/">Back to Home</a></div>
    </div>`;
}

async function renderConnections() {
  if (!SOCIAL_ENABLED) return renderComingSoon();
  setCrumbs([{ label: "Social accounts" }]);
  view.innerHTML = `<div class="soc-grid">${Array(4).fill('<div class="skeleton" style="height:260px"></div>').join("")}</div>`;
  const list = await api("/api/social");
  view.innerHTML = `
    <div class="lib-head"><div><h1 style="margin:0">Social accounts</h1>
      <div class="muted" style="font-size:.88rem;margin-top:4px">Connect your channels to track growth in Analytics.</div></div></div>
    <div class="notice">${icon("info")}<div>Connect your accounts once, then press <b>Post</b> on any rendered clip to publish it to all of them at the same time.
      Importing videos from links doesn't need a connection. Tokens stay on this server and are never sent to the browser.</div></div>
    <div class="soc-grid" id="soc">${list.map(connectionCard).join("")}</div>
    <div class="section-head"><h2>Recent posts</h2></div>
    <div id="post-history"><div class="skeleton" style="height:70px"></div></div>`;
  loadPostHistory();
  $("#soc").onclick = async e => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const id = b.dataset.id, item = list.find(x => x.id === id);
    if (b.dataset.act === "connect") connectPopup(id);
    if (b.dataset.act === "setup") setupGuide(item);
    if (b.dataset.act === "refresh") {
      b.disabled = true; b.innerHTML = `${icon("refresh")} Refreshing…`;
      try { await api(`/api/social/${id}/refresh`, { method: "POST" }); toast(`${item.name} stats updated`); } catch (err) { fail(err); }
      renderConnections();
    }
    if (b.dataset.act === "disconnect" && await confirmBox(`Disconnect ${item.name}?`, "ClipForge will forget this account and its saved stats.", "Disconnect")) {
      await api(`/api/social/${id}`, { method: "DELETE" }).catch(fail); toast(`${item.name} disconnected`); renderConnections(); updateConnDot();
    }
  };
}
function connectionCard(s) {
  const pl = plat(s.id), st = s.stats || {};
  const head = `
    <div class="glow" style="background:${pl.color}"></div>
    <div class="soc-top"><span class="bico" style="background:${pl.bg}">${platSvg(s.id, 22)}</span>
      <div><div class="nm">${esc(s.name)}</div>
      <div class="status ${s.connected ? (s.error ? "err" : "on") : ""}">${s.connected ? (s.error ? "Needs attention" : "Connected") : s.configured ? "Not connected" : "Setup required"}</div></div></div>`;
  if (s.connected) {
    const cells = [["followers", "Followers"], ["views", "Views"], ["likes", "Likes"], ["posts", "Posts"], ["following", "Following"]].filter(([k]) => st[k] != null).slice(0, 3);
    return `<div class="soc">${head}
      <div class="who">${s.profile?.avatar ? `<img src="${esc(s.profile.avatar)}" alt="" referrerpolicy="no-referrer" />` : ""}
        <div style="min-width:0"><div class="h">${esc(s.profile?.name || "")}</div>${s.profile?.url ? `<a href="${esc(s.profile.url)}" target="_blank" rel="noopener">${esc(s.profile.handle || "View profile")} ↗</a>` : `<span class="dim">${esc(s.profile?.handle || "")}</span>`}</div></div>
      <div class="sstats">${cells.map(([k, l]) => `<div><b>${num(st[k])}</b><span>${l}</span></div>`).join("")}</div>
      ${s.error ? `<p class="hint" style="color:var(--bad);margin:0">${esc(s.error)}</p>` : `<p class="hint" style="margin:0">Updated ${s.updated_at ? ago(s.updated_at) : "never"}</p>`}
      <div class="pubstate ${s.can_publish ? "on" : ""}">${icon(s.can_publish ? "send" : "info")}${s.can_publish ? "Posting enabled" : "Posting not allowed yet: reconnect to grant permission"}</div>
      <div class="actions"><button class="btn sm" data-act="refresh" data-id="${s.id}">${icon("refresh")} Refresh</button>
        ${s.error || !s.can_publish ? `<button class="btn sm ${s.can_publish ? "" : "accent"}" data-act="connect" data-id="${s.id}">Reconnect</button>` : ""}
        <button class="btn ghost sm danger" data-act="disconnect" data-id="${s.id}">Disconnect</button></div>
    </div>`;
  }
  return `<div class="soc">${head}
    <p class="muted" style="margin:0;font-size:.9rem">${SOCIAL_COPY[s.id] || ""}</p>
    <div class="actions">${s.configured
      ? `<button class="btn primary" data-act="connect" data-id="${s.id}">${icon("plug")} Connect ${esc(s.name)}</button>`
      : `<button class="btn" data-act="setup" data-id="${s.id}">${icon("info")} How to set up</button>`}</div>
  </div>`;
}
function connectPopup(id) {
  const w = 520, h = 720, left = screenX + (outerWidth - w) / 2, top = screenY + (outerHeight - h) / 2;
  const pop = window.open(`/api/social/${id}/connect`, "clipforge-oauth", `width=${w},height=${h},left=${left},top=${top}`);
  if (!pop) { location.href = `/api/social/${id}/connect`; return; }
  const timer = setInterval(() => { if (pop.closed) { clearInterval(timer); if (location.hash === "#/connections") renderConnections(); updateConnDot(); } }, 700);
}
window.addEventListener("message", e => {
  if (e.data?.type !== "clipforge-social") return;
  toast(e.data.message, 4000, !e.data.ok);
  if (location.hash === "#/connections") renderConnections();
  updateConnDot();
});
function setupGuide(s) {
  const su = s.setup;
  openModal(`
    <div class="modal-head"><h2>Set up ${esc(s.name)}</h2><button class="icon-btn" data-close aria-label="Close" data-icon="x"></button></div>
    <p class="muted" style="font-size:.9rem">Each network needs a free developer app. This is a one-time setup by whoever runs this ClipForge server.</p>
    <ol class="steps">${su.steps.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
    <label style="margin-bottom:0">Redirect URI</label>
    <div class="copyrow"><code id="m-uri">${esc(su.redirect_uri)}</code><button class="btn sm" id="m-copy">${icon("copy")} Copy</button></div>
    ${su.https_only && su.redirect_uri.startsWith("http://") ? `<p class="hint" style="color:var(--warn)">${esc(s.name)} only accepts https redirect URIs. Run a tunnel (e.g. <code class="env">cloudflared tunnel --url http://127.0.0.1:8000</code>) and set <code class="env">PUBLIC_URL</code> to the https address.</p>` : ""}
    <p class="hint">Then add these to <code class="env">backend/.env</code> and restart ClipForge:</p>
    <div class="copyrow"><code>${esc(su.env[0])}=…<br>${esc(su.env[1])}=…</code></div>
    <div class="row end"><a class="btn primary" href="${esc(su.console_url)}" target="_blank" rel="noopener">${icon("external")} Open developer console</a></div>`,
    b => { $("#m-copy", b).onclick = async () => { try { await navigator.clipboard.writeText(su.redirect_uri); toast("Redirect URI copied"); } catch { toast("Copy blocked: select the text instead", 3000, true); } }; });
}
async function updateConnDot() {
  try { const l = await api("/api/social"); $("#conn-dot").hidden = !l.some(s => s.connected && s.error); } catch {}
}

// ============================================================= publish ==
let POSTED = {};   // clip id -> {platform: {state, url}}
async function loadPosted(pid) {
  POSTED = {};
  const posts = await api(`/api/posts?project_id=${pid}&limit=200`).catch(() => []);
  posts.slice().reverse().forEach(p => Object.entries(p.targets).forEach(([net, t]) => {
    if (t.state === "error") return;
    (POSTED[p.clip_id] ||= {})[net] = { state: t.state, url: t.url };
  }));
}
function postedBadges(cid) {
  const m = POSTED[cid]; if (!m) return "";
  return `<div class="posted">${Object.entries(m).map(([net, t]) => t.url
    ? `<a href="${esc(t.url)}" target="_blank" rel="noopener" title="View on ${esc(plat(net).name)}">${platSvg(net, 14)}</a>`
    : `<span class="pn" title="${esc(plat(net).name)}: ${esc(t.state)}">${platSvg(net, 14)}</span>`).join("")}<span>Posted</span></div>`;
}

const PRIV = {
  youtube: [["public", "Public"], ["unlisted", "Unlisted"], ["private", "Private"]],
  tiktok: [["public", "Everyone"], ["friends", "Friends"], ["followers", "Followers"], ["private", "Only me"]],
};
async function openPublish(p, c) {
  const accounts = await api("/api/social").catch(() => []);
  const limits = INFO?.publish_limits || {};
  const length = c.end - c.start;
  const remembered = lsGet("clipforge.publish.targets", null);
  const privPref = lsGet("clipforge.publish.privacy", {});
  const fits = id => !limits[id] || (length >= limits[id].min && length <= limits[id].max);
  const usable = a => a.connected && a.can_publish && fits(a.id);
  const selected = new Set(accounts.filter(a => usable(a) && (!remembered || remembered.includes(a.id))).map(a => a.id));
  const defCaption = [c.hook && c.hook !== c.title ? c.hook : c.title, (c.hashtags || []).join(" ")].filter(Boolean).join("\n\n");

  const tile = a => {
    const lim = limits[a.id];
    let why = "";
    if (!a.configured) why = "Not set up";
    else if (!a.connected) why = "Not connected";
    else if (!a.can_publish) why = "Reconnect to allow posting";
    else if (!fits(a.id)) why = `Clip must be ${lim.min}–${lim.max}s`;
    return `<button type="button" class="ptile" data-net="${a.id}" aria-pressed="${selected.has(a.id)}" ${why ? "disabled" : ""}>
      <span class="bico" style="background:${plat(a.id).bg}">${platSvg(a.id, 20)}</span>
      <span class="pt-txt"><b>${esc(a.name)}</b><small>${why ? esc(why) : esc(a.profile?.handle || a.profile?.name || "Connected")}</small></span>
      <span class="pt-check">${icon("check")}</span></button>`;
  };
  const anyUsable = accounts.some(usable);

  await openModal(`
    <div class="modal-head"><h2>Post clip</h2><button class="icon-btn" data-close aria-label="Close">${icon("x")}</button></div>
    <div class="pub-grid">
      <div class="pub-prev"><video src="/media/${p.id}/clips/${c.render.file}?v=${c.render.at}" poster="/media/${p.id}/clips/${c.render.thumb}?v=${c.render.at}" controls playsinline preload="none"></video>
        <div class="hint">${esc(c.title)} · ${length.toFixed(0)}s · ${esc(c.render.settings?.aspect || "9:16")}</div></div>
      <form id="pub-form">
        <label style="margin-top:0">Post to</label>
        <div class="ptiles">${accounts.map(tile).join("")}</div>
        ${anyUsable ? "" : `<p class="hint">No account can post yet. <a href="#/connections" data-close>Connect your accounts</a> first.</p>`}
        <label>Caption <span class="dim" id="cap-count"></span>
          <textarea id="pub-caption" rows="4" maxlength="5000">${esc(defCaption)}</textarea></label>
        <label id="yt-title-wrap">YouTube title
          <input id="pub-title" maxlength="100" value="${esc((c.title || "").slice(0, 90) + " #Shorts")}" /></label>
        <div class="row" id="priv-row" style="margin:4px 0 0">
          ${Object.entries(PRIV).map(([net, opts]) => `<label class="grow" data-priv="${net}" style="margin:0">${esc(plat(net).name)} visibility
            <select data-privsel="${net}">${opts.map(([v, l]) => `<option value="${v}" ${(privPref[net] || "public") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>`).join("")}
        </div>
        <p class="hint" id="pub-warn"></p>
        <div class="row end"><button type="button" class="btn ghost" data-close>Cancel</button>
          <button class="btn primary" id="pub-go">${icon("send")} Post</button></div>
      </form>
    </div>`, (b, finish) => {
      const sync = () => {
        $$(".ptile", b).forEach(t => t.setAttribute("aria-pressed", selected.has(t.dataset.net)));
        const n = selected.size, cap = $("#pub-caption", b).value;
        $("#pub-go", b).innerHTML = `${icon("send")} ${n ? `Post to ${n} account${n > 1 ? "s" : ""}` : "Pick an account"}`;
        $("#pub-go", b).disabled = !n;
        $("#yt-title-wrap", b).hidden = !selected.has("youtube");
        $$("[data-priv]", b).forEach(el => { el.hidden = !selected.has(el.dataset.priv); });
        $("#priv-row", b).hidden = !["youtube", "tiktok"].some(x => selected.has(x));
        const tight = [...selected].map(x => [x, limits[x]?.caption]).filter(([, l]) => l).sort((a, z) => a[1] - z[1])[0];
        $("#cap-count", b).textContent = `${cap.length}${tight ? ` / ${tight[1]} (${plat(tight[0]).name})` : ""}`;
        const over = [...selected].filter(x => limits[x] && cap.length > limits[x].caption);
        const notes = [];
        if (over.length) notes.push(`Caption will be cut to fit ${over.map(x => plat(x).name).join(", ")}.`);
        if ((c.render.settings?.aspect || "9:16") !== "9:16" && ["tiktok", "instagram", "youtube"].some(x => selected.has(x)))
          notes.push("Tip: TikTok, Reels and Shorts look best in 9:16. Re-render this clip in 9:16 for full-screen video.");
        $("#pub-warn", b).textContent = notes.join(" ");
      };
      $(".ptiles", b).onclick = e => {
        const t = e.target.closest(".ptile"); if (!t || t.disabled) return;
        if (selected.has(t.dataset.net)) selected.delete(t.dataset.net); else selected.add(t.dataset.net);
        sync();
      };
      $("#pub-caption", b).oninput = sync;
      $("#pub-form", b).onsubmit = async e => {
        e.preventDefault();
        const targets = [...selected]; if (!targets.length) return;
        const options = {};
        $$("[data-privsel]", b).forEach(sel => { options[sel.dataset.privsel] = { privacy: sel.value }; privPref[sel.dataset.privsel] = sel.value; });
        lsSet("clipforge.publish.targets", targets); lsSet("clipforge.publish.privacy", privPref);
        const go = $("#pub-go", b); go.disabled = true; go.textContent = "Starting…";
        try {
          const post = await api("/api/publish", { method: "POST", body: {
            project_id: p.id, clip_id: c.id, targets, caption: $("#pub-caption", b).value, title: $("#pub-title", b).value, options } });
          showPublishProgress(b, post, finish);
        } catch (err) { fail(err); go.disabled = false; sync(); }
      };
      sync();
    }, "pub");
  if (current?.id === p.id && $("#clips")) { await loadPosted(p.id); $$("#clips .clip-card").forEach(el => { el.dataset.key = ""; }); refresh(); }
}

const PSTATE = { queued: "Waiting", uploading: "Uploading", processing: "Processing", done: "Posted", error: "Failed" };
function publishRows(post) {
  return Object.entries(post.targets).map(([net, t]) => `
    <div class="prow ${t.state}">
      <span class="bico" style="background:${plat(net).bg}">${platSvg(net, 18)}</span>
      <div class="pr-main">
        <div class="pr-top"><b>${esc(plat(net).name)}</b><span class="pr-state">${t.state === "uploading" ? `Uploading ${Math.round(t.progress * 100)}%` : PSTATE[t.state] || t.state}</span></div>
        ${t.state === "error" ? `<div class="hint" style="color:var(--bad);margin-top:4px">${esc(t.error)}</div>` :
          t.state === "done" ? (t.note ? `<div class="hint" style="margin-top:4px">${esc(t.note)}</div>` : "") :
          `<div class="progress ${t.state === "processing" || t.state === "queued" ? "indet" : ""}" style="margin-top:8px"><div style="width:${Math.round(t.progress * 100)}%"></div></div>`}
      </div>
      ${t.state === "done" && t.url ? `<a class="btn sm" href="${esc(t.url)}" target="_blank" rel="noopener">${icon("external")} View</a>` : ""}
    </div>`).join("");
}
function showPublishProgress(b, post, finish) {
  b.innerHTML = `
    <div class="modal-head"><h2>Posting “${esc(post.clip_title)}”</h2><button class="icon-btn" id="pp-x" aria-label="Close">${icon("x")}</button></div>
    <p class="hint">Uploads run on the server. You can close this window; progress is kept under Social accounts → Recent posts.</p>
    <div class="prows" id="pp-rows" aria-live="polite">${publishRows(post)}</div>
    <div class="row end"><button class="btn primary" id="pp-done">Done</button></div>`;
  $("#pp-x", b).onclick = $("#pp-done", b).onclick = () => finish(true);
  let notified = false;
  const tick = async () => {
    if (!$("#pp-rows")) return;
    const p = await api(`/api/posts/${post.id}`).catch(() => null);
    if (!p || !$("#pp-rows")) return;
    $("#pp-rows").innerHTML = publishRows(p);
    const states = Object.values(p.targets).map(t => t.state);
    if (states.every(st => st === "done" || st === "error")) {
      if (!notified) {
        notified = true;
        const ok = states.filter(st => st === "done").length;
        toast(ok === states.length ? `Posted to ${ok} account${ok > 1 ? "s" : ""}` : `${ok} of ${states.length} posts succeeded`, 4000, ok < states.length);
      }
      return;
    }
    setTimeout(tick, 1200);
  };
  setTimeout(tick, 800);
}

async function loadPostHistory() {
  const el = $("#post-history"); if (!el) return;
  const posts = await api("/api/posts?limit=20").catch(() => []);
  if (!$("#post-history")) return;
  el.innerHTML = posts.length ? `<div class="hist">${posts.map(p => `
    <div class="hrow">
      ${p.thumb ? `<img src="/media/${p.project_id}/clips/${p.thumb}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" />` : `<span class="th-ph">${icon("film")}</span>`}
      <div class="h-main"><a href="#/p/${p.project_id}" class="t1">${esc(p.clip_title)}</a><div class="t2">${ago(p.created)}</div></div>
      <div class="h-nets">${Object.entries(p.targets).map(([net, t]) => {
        const label = `${plat(net).name}: ${PSTATE[t.state] || t.state}${t.error ? " – " + t.error : ""}`;
        const inner = `${platSvg(net, 16)}<i class="dotst ${t.state}"></i>`;
        return t.url ? `<a href="${esc(t.url)}" target="_blank" rel="noopener" title="${esc(label)}" class="hnet">${inner}</a>` : `<span class="hnet" title="${esc(label)}">${inner}</span>`;
      }).join("")}</div>
    </div>`).join("")}</div>`
    : `<div class="empty"><div class="ico">${icon("send")}</div>Nothing posted yet. Open a project and press <b>Post</b> on a rendered clip.</div>`;
  if (posts.some(p => Object.values(p.targets).some(t => ["queued", "uploading", "processing"].includes(t.state))))
    setTimeout(loadPostHistory, 3000);
}

// =========================================================== public pages ==
let ME = null;
const pub = $("#public");
function showPublic(on) {
  pub.hidden = !on; $("#shell").hidden = on;
  if (!on) pub.innerHTML = "";   // don't leave a filled-in auth form (password!) lying in the DOM
  document.body.classList.toggle("is-public", on);
}

const FEATURES = [
  ["link", "Paste any link", "YouTube, TikTok, Instagram, X, Twitch, Vimeo or Google Drive. Or drop in a file up to 4 GB."],
  ["sparkle", "Finds the viral moments", "Audio spikes, scene cuts, hype words and an optional AI pass rank every moment with a virality score."],
  ["cc", "Animated captions", "Word-by-word captions burned in, in four styles, plus a hook title for the first three seconds."],
  ["crop", "Reframed for vertical", "9:16, 1:1, 4:5 or 16:9 with blurred fill, smart crop or letterbox, all in one render pass."],
  ["folder", "Organised in folders", "Keep streams, podcasts and client work apart. Drag projects between folders and search everything."],
  ["chart", "Analytics", "See what you've produced, your score distribution, top clips and the hashtags that keep coming up."],
];
const DEMO_CLIPS = [
  { score: 94, words: ["NO", "WAY", "HE", "DID", "THAT"], hot: 1, title: "The jump nobody expected", hue: 250 },
  { score: 88, words: ["THIS", "CHANGED", "EVERYTHING"], hot: 1, title: "Why I quit my job", hue: 330 },
  { score: 81, words: ["WATCH", "THE", "LEFT", "SIDE"], hot: 2, title: "Clutch 1v4 in overtime", hue: 160 },
];

function renderLanding() {
  setCrumbs([]);
  pub.innerHTML = `
  <div class="lp">
    <header class="lp-nav">
      <a class="brand" href="#/" aria-label="ClipForge home"><span class="logo">${icon("play")}</span><span>ClipForge</span></a>
      <nav class="lp-links" aria-label="Page sections">
        <button data-scroll="features">Features</button><button data-scroll="how">How it works</button><button data-scroll="pricing">Pricing</button>
      </nav>
      <div class="lp-actions"><a class="btn ghost" href="#/signin">Sign in</a><a class="btn primary" href="#/signup">Get started</a></div>
    </header>

    <section class="lp-hero">
      <span class="eyebrow">${icon("sparkle")} AI video clipping</span>
      <h1>Long videos in.<br><em>Viral shorts</em> out.</h1>
      <p class="lead">Paste a link or upload a file. ClipForge finds the moments worth watching, reframes them for vertical and adds animated captions. One click.</p>
      <div class="cta"><a class="btn primary lg" href="#/signup">Create your account</a><a class="btn ghost lg" href="#/signin">Sign in</a></div>
      <div class="works-with">Works with <span class="plats">${["youtube", "tiktok", "instagram", "x", "twitch", "facebook", "vimeo", "drive"].map(p => `<span title="${plat(p).name}">${platSvg(p, 20)}</span>`).join("")}</span></div>

      <div class="lp-demo" aria-hidden="true">
        <div class="demo-bar"><span class="plat-slot">${platSvg("youtube", 18)}</span><span class="demo-url">youtube.com/watch?v=my-3-hour-stream</span><span class="demo-btn">Get clips in 1 click</span></div>
        <div class="demo-clips">${DEMO_CLIPS.map((c, i) => `
          <div class="demo-clip" style="--h:${c.hue};--d:${i * 0.12}s">
            <div class="phone"><span class="dscore">${c.score}</span>
              <div class="dcap">${c.words.map((w, k) => `<span class="${k === c.hot ? "hot" : ""}">${w}</span>`).join(" ")}</div></div>
            <div class="dtitle">${c.title}</div>
          </div>`).join("")}</div>
      </div>
    </section>

    <section class="lp-sec" id="features">
      <h2>Everything between the long video and the post</h2>
      <p class="sub">No timeline scrubbing, no manual captions, no resizing in three different apps.</p>
      <div class="feat-grid">${FEATURES.map(([ic, h, t]) => `
        <article class="feat"><span class="fi">${icon(ic)}</span><h3>${h}</h3><p>${t}</p></article>`).join("")}</div>
    </section>

    <section class="lp-sec" id="how">
      <h2>Three steps</h2>
      <ol class="steps3">
        <li><b>1</b><h3>Drop your video</h3><p>Paste a link to a stream, podcast or vlog, or upload the file.</p></li>
        <li><b>2</b><h3>Get ranked clips</h3><p>ClipForge transcribes, scores every moment and renders the best ones with captions.</p></li>
        <li><b>3</b><h3>Tweak and download</h3><p>Trim, restyle captions or change the format, then download ready-to-post shorts.</p></li>
      </ol>
    </section>

    ${pricingSection()}

    <section class="lp-final">
      <h2>Your next viral clip is already in your footage.</h2>
      <p class="sub">Create an account and turn your first video into shorts.</p>
      <div class="cta"><a class="btn primary lg" href="#/signup">Get started</a></div>
    </section>

    <footer class="lp-foot"><span class="brand"><span class="logo">${icon("play")}</span>ClipForge</span>
      <span class="dim">Clip footage you own or have rights to.</span></footer>
  </div>`;
  pub.onclick = e => {
    const b = e.target.closest("[data-scroll]"); if (!b) return;
    document.getElementById(b.dataset.scroll)?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  };
  document.title = "ClipForge · viral shorts from long videos";
}

// ============================================================= billing ==
const money = n => (n % 1 ? n.toFixed(2) : String(n));
function planPrice(p, interval) {
  if (!p.month) return `<div class="pp"><b>$0</b><span>forever</span></div>`;
  return interval === "year"
    ? `<div class="pp"><b>$${money(p.year)}</b><span>/ year</span></div><div class="pp-sub">$${money(p.year / 12)} a month, billed yearly</div>`
    : `<div class="pp"><b>$${money(p.month)}</b><span>/ month</span></div><div class="pp-sub">or $${money(p.year)} a year (2 months free)</div>`;
}
function planCard(p, interval, cta) {
  return `
    <article class="plan ${p.popular ? "popular" : ""}">
      ${p.popular ? `<span class="plan-badge">Most popular</span>` : ""}
      <h3>${esc(p.name)}</h3>
      <p class="muted plan-tag">${esc(p.tagline)}</p>
      ${planPrice(p, interval)}
      ${cta}
      <ul>${p.features.map(f => `<li>${icon("check")}${esc(f)}</li>`).join("")}</ul>
    </article>`;
}
const intervalToggle = interval => `
  <div class="range billing-toggle" role="group" aria-label="Billing period">
    <button data-int="month" aria-pressed="${interval === "month"}">Monthly</button>
    <button data-int="year" aria-pressed="${interval === "year"}">Yearly <span class="save">2 months free</span></button>
  </div>`;

function pricingSection() {
  const plans = INFO?.plans; if (!plans?.length) return "";
  let interval = "month";
  setTimeout(() => {
    const sec = $("#pricing"); if (!sec) return;
    sec.onclick = e => {
      const b = e.target.closest("[data-int]"); if (!b) return;
      interval = b.dataset.int;
      $(".billing-toggle", sec).outerHTML = intervalToggle(interval);
      $(".plan-grid", sec).innerHTML = plans.map(p => planCard(p, interval, `<a class="btn ${p.popular ? "primary" : ""} block" href="#/signup">${p.month ? `Start with ${esc(p.name)}` : "Start free"}</a>`)).join("");
    };
  });
  return `
    <section class="lp-sec" id="pricing">
      <h2>Simple pricing</h2>
      <p class="sub">Start free. Upgrade when you're clipping every week. Cancel anytime.</p>
      <div style="text-align:center;margin-top:22px">${intervalToggle(interval)}</div>
      <div class="plan-grid">${plans.map(p => planCard(p, interval, `<a class="btn ${p.popular ? "primary" : ""} block" href="#/signup">${p.month ? `Start with ${esc(p.name)}` : "Start free"}</a>`)).join("")}</div>
    </section>`;
}

const fmtDate = iso => iso ? new Date(iso).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }) : "";
async function renderBilling() {
  setCrumbs([{ label: "Plans & billing" }]);
  view.innerHTML = `<div class="skeleton" style="height:140px;margin-bottom:18px"></div><div class="plan-grid">${Array(3).fill('<div class="skeleton" style="height:380px"></div>').join("")}</div>`;
  const b = await api("/api/billing");
  let interval = b.interval || lsGet("clipforge.interval", "month");
  const cur = b.plans.find(p => p.id === b.plan);
  const paid = b.plan !== "free";

  const statusLine = () => {
    if (!paid) return `<span class="chip-st">Free plan</span>`;
    if (b.status === "past_due") return `<span class="chip-st bad">${icon("alert")} Payment failed: update your card</span>`;
    if (b.cancel_at_period_end) return `<span class="chip-st warn">Ends ${fmtDate(b.current_period_end)}</span>`;
    return `<span class="chip-st ok">${b.status === "trialing" ? "Trial" : "Active"} · renews ${fmtDate(b.current_period_end)}</span>`;
  };
  const u = b.usage, pct = u.limit ? Math.min(100, (u.videos / u.limit) * 100) : 0;

  const ctaFor = p => {
    if (!b.stripe_ready && p.id !== "free") return `<button class="btn block" disabled>Not available yet</button>`;
    if (p.id === b.plan) return `<button class="btn block" disabled>${icon("check")} Current plan</button>`;
    if (!paid) return `<button class="btn ${p.popular ? "primary" : ""} block" data-buy="${p.id}">Upgrade to ${esc(p.name)}</button>`;
    if (p.id === "free") return `<button class="btn ghost block" data-portal>Cancel in billing portal</button>`;
    return `<button class="btn block" data-portal>Switch in billing portal</button>`;
  };

  const draw = () => {
    view.innerHTML = `
      <div class="lib-head"><div><h1 style="margin:0">Plans & billing</h1>
        <div class="muted" style="font-size:.88rem;margin-top:4px">Payments are handled securely by Stripe.</div></div></div>
      ${!b.stripe_ready ? `<div class="notice">${icon("info")}<div>Payments aren't switched on yet. Add <code class="env">STRIPE_SECRET_KEY</code> to <code class="env">backend/.env</code>, run <code class="env">scripts/stripe_setup.py</code> and restart ClipForge.</div></div>` : ""}
      ${b.test_mode ? `<div class="notice">${icon("info")}<div><b>Test mode.</b> No real money moves. Pay with card <code class="env">4242 4242 4242 4242</code>, any future date and any CVC.</div></div>` : ""}

      <section class="panel cur-plan">
        <div>
          <div class="hint" style="margin:0">Current plan</div>
          <div class="cp-name">${esc(cur?.name || "Free")}${paid && b.interval ? `<span class="dim"> · ${b.interval === "year" ? "yearly" : "monthly"}</span>` : ""}</div>
          ${statusLine()}
        </div>
        <div class="cp-usage">
          <div class="cp-u-top"><span>Videos this month</span><b>${u.videos}${u.limit ? ` / ${u.limit}` : ""}</b></div>
          ${u.limit ? `<div class="progress ${pct >= 100 ? "full" : ""}"><div style="width:${pct}%"></div></div>
            <div class="hint" style="margin:6px 0 0">${pct >= 100 ? "You've reached this month's limit." : `${u.limit - u.videos} left · resets on the 1st`}</div>`
            : `<div class="hint" style="margin:6px 0 0">Unlimited on your plan.</div>`}
        </div>
        <div class="cp-actions">${b.has_customer && b.stripe_ready ? `<button class="btn" data-portal>${icon("external")} Manage billing</button>` : ""}</div>
      </section>

      <div style="text-align:center;margin:26px 0 4px">${intervalToggle(interval)}</div>
      <div class="plan-grid">${b.plans.map(p => planCard(p, interval, ctaFor(p))).join("")}</div>

      <section class="faq">
        <details><summary>Can I cancel anytime?</summary><p>Yes. Open <b>Manage billing</b>, cancel, and you keep your plan until the end of the period you paid for. Then you're back on Free.</p></details>
        <details><summary>What counts as a video?</summary><p>Every link you import or file you upload counts once, however many clips you make from it. The count resets on the 1st of each month.</p></details>
        <details><summary>How do I change card or get invoices?</summary><p><b>Manage billing</b> opens Stripe's secure portal, where you can update your card, switch plans and download receipts.</p></details>
      </section>`;
  };
  draw();

  view.onclick = async e => {
    const t = e.target.closest("[data-int],[data-buy],[data-portal]"); if (!t) return;
    if (t.dataset.int) { interval = t.dataset.int; lsSet("clipforge.interval", interval); draw(); hydrateIcons(view); return; }
    t.disabled = true; const label = t.innerHTML; t.textContent = "Opening Stripe…";
    try {
      const r = t.dataset.buy
        ? await api("/api/billing/checkout", { method: "POST", body: { plan: t.dataset.buy, interval } })
        : await api("/api/billing/portal", { method: "POST" });
      location.href = r.url;
    } catch (err) { fail(err); t.disabled = false; t.innerHTML = label; }
  };
}

async function usageNote() {
  const el = $("#usage-note"); if (!el) return;
  const b = await api("/api/billing").catch(() => null);
  if (!b || !$("#usage-note") || !b.usage.limit) return;
  const left = b.usage.limit - b.usage.videos;
  el.innerHTML = left > 0
    ? `${icon("film")} ${left} of ${b.usage.limit} ${esc(b.plans.find(p => p.id === b.plan)?.name || "")} videos left this month · <a href="#/billing">${b.plan === "free" ? "Upgrade" : "Plans"}</a>`
    : `${icon("alert")} You've used all ${b.usage.limit} videos this month · <a href="#/billing">Upgrade to keep going</a>`;
  el.hidden = false;
  el.classList.toggle("out", left <= 0);
}

// ------------------------------------------------------- Supabase auth --
let SB = null;   // supabase-js client (browser side: publishable key only)

function friendlyAuthError(e) {
  const m = (e?.message || String(e || "")).toLowerCase();
  if (m.includes("invalid login credentials")) return "Email or password is incorrect.";
  if (m.includes("email not confirmed")) return "Please confirm your email first. Check your inbox for the link we sent.";
  if (m.includes("already registered") || m.includes("already been registered")) return "An account with this email already exists. Try signing in.";
  if (m.includes("rate limit") || m.includes("too many")) return "Too many attempts. Wait a few minutes and try again.";
  if (m.includes("password should be") || m.includes("weak password")) return "That password is too weak. Use at least 8 characters with a mix of letters and numbers.";
  if (m.includes("failed to fetch") || m.includes("network")) return "Can't reach the sign-in service. Check your internet connection.";
  return e?.message || "Something went wrong. Please try again.";
}

async function syncSession(session) {
  const r = await api("/api/auth/session", { method: "POST", body: { access_token: session.access_token } });
  ME = r.user;
  return ME;
}

function authShell(inner) {
  return `
  <div class="auth">
    <aside class="auth-art">
      <a class="brand" href="#/"><span class="logo">${icon("play")}</span><span>ClipForge</span></a>
      <div class="art-body">
        <h2>Your next viral clip is already in your footage.</h2>
        <ul>${["Paste a link or upload a file", "Clips ranked by virality score", "Animated captions and vertical reframing", "Folders and analytics for everything you make"]
          .map(t => `<li>${icon("check")}${t}</li>`).join("")}</ul>
      </div>
      <div class="art-clips" aria-hidden="true">${DEMO_CLIPS.map((c, i) => `<div class="phone sm" style="--h:${c.hue};--r:${(i - 1) * 7}deg"><span class="dscore">${c.score}</span></div>`).join("")}</div>
    </aside>
    <main class="auth-main">
      <a class="auth-back" href="#/">${icon("home")} Back to home</a>
      <div class="auth-card">
        <a class="brand only-small" href="#/"><span class="logo">${icon("play")}</span><span>ClipForge</span></a>
        ${!SB || INFO?.server_ready === false ? `<div class="auth-err" role="alert" style="margin:0 0 16px">The server isn't fully set up yet: ${!SB ? "Supabase settings are missing" : "SUPABASE_SECRET_KEY is missing"} in backend/.env. Accounts will work once it's added and ClipForge is restarted.</div>` : ""}
        ${inner}
      </div>
    </main>
  </div>`;
}

const pwField = (id, label, auto, extra = "") => `
  <label>${label}
    <span class="pw"><input id="${id}" type="password" autocomplete="${auto}" maxlength="256" required ${extra} />
    <button type="button" class="icon-btn" data-show="${id}" aria-label="Show password" aria-pressed="false">${icon("eye")}</button></span>
  </label>`;

function bindPwTools(root, meterFor) {
  root.querySelectorAll("[data-show]").forEach(b => b.onclick = () => {
    const pw = $(`#${b.dataset.show}`), show = pw.type === "password"; pw.type = show ? "text" : "password";
    b.setAttribute("aria-pressed", show); b.setAttribute("aria-label", show ? "Hide password" : "Show password");
    b.innerHTML = icon(show ? "eyeOff" : "eye");
  });
  const pw = meterFor && $(`#${meterFor}`);
  if (pw) pw.oninput = () => {
    const v = pw.value, score = (v.length >= 8) + (v.length >= 12) + (/[A-Z]/.test(v) && /[a-z]/.test(v) && /\d|[^\w]/.test(v));
    $$(".pw-meter i").forEach((el, i) => el.classList.toggle("on", i < score));
    $(".pw-meter").dataset.s = score;
    $("#pw-hint").textContent = v.length < 8 ? `At least 8 characters (${8 - v.length} to go).` : ["", "Okay password.", "Good password.", "Strong password."][score];
  };
}

function renderNotice(title, html, cta = `<a class="btn primary lg block" href="#/signin">Back to sign in</a>`) {
  pub.innerHTML = authShell(`
    <div class="auth-ico">${icon("send")}</div>
    <h1>${title}</h1><p class="muted">${html}</p>${cta}`);
}

function renderAuth(mode) {
  const up = mode === "signup", forgot = mode === "forgot", reset = mode === "reset";
  document.title = `${up ? "Create account" : forgot ? "Reset password" : reset ? "Choose a new password" : "Sign in"} · ClipForge`;
  const heading = up ? "Create your account" : forgot ? "Reset your password" : reset ? "Choose a new password" : "Welcome back";
  const sub = up ? "Start turning long videos into shorts." : forgot ? "Enter your email and we'll send you a reset link."
    : reset ? "Pick a new password for your account." : "Sign in to your ClipForge workspace.";
  pub.innerHTML = authShell(`
    <form id="auth-form" novalidate>
      <h1>${heading}</h1>
      <p class="muted">${sub}</p>
      ${up ? `<label>Name<input id="a-name" autocomplete="name" maxlength="60" required /></label>` : ""}
      ${reset ? "" : `<label>Email<input id="a-email" type="email" autocomplete="email" inputmode="email" maxlength="254" required /></label>`}
      ${up || reset ? pwField("a-pw", reset ? "New password" : "Password", "new-password", 'minlength="8"') +
        `<div class="pw-meter" aria-hidden="true"><i></i><i></i><i></i></div><p class="hint" id="pw-hint">At least 8 characters.</p>` : ""}
      ${!up && !forgot && !reset ? pwField("a-pw", "Password", "current-password") + `<a class="forgot" href="#/forgot">Forgot password?</a>` : ""}
      <div class="auth-err" id="a-err" role="alert" hidden></div>
      <button class="btn primary lg block" id="a-go">${up ? "Create account" : forgot ? "Send reset link" : reset ? "Save new password" : "Sign in"}</button>
      <p class="switch">${up ? `Already have an account? <a href="#/signin">Sign in</a>`
        : forgot ? `Remembered it? <a href="#/signin">Sign in</a>`
        : reset ? "" : `New to ClipForge? <a href="#/signup">Create an account</a>`}</p>
    </form>`);
  const form = $("#auth-form"), err = $("#a-err");
  bindPwTools(pub, up || reset ? "a-pw" : null);
  setTimeout(() => (up ? $("#a-name") : reset ? $("#a-pw") : $("#a-email")).focus());
  const showErr = m => { err.textContent = m; err.hidden = false; };
  const label = $("#a-go").textContent;

  form.onsubmit = async e => {
    e.preventDefault(); err.hidden = true;
    if (!SB) return showErr("Sign-in isn't available: the server's Supabase settings are missing.");
    const email = $("#a-email")?.value.trim() || "", password = $("#a-pw")?.value || "", name = $("#a-name")?.value.trim() || "";
    if (up && !name) return showErr("Please enter your name."), $("#a-name").focus();
    if (!reset && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return showErr("Please enter a valid email address."), $("#a-email").focus();
    if ((up || reset) && password.length < 8) return showErr("Use at least 8 characters for your password."), $("#a-pw").focus();
    if (!forgot && !password) return showErr("Please enter your password."), $("#a-pw").focus();
    const go = $("#a-go"); go.disabled = true; go.textContent = "Please wait…";
    try {
      if (forgot) {
        const { error } = await SB.auth.resetPasswordForEmail(email, { redirectTo: `${location.origin}/?reset=1` });
        if (error) throw error;
        return renderNotice("Check your email", `If an account exists for <b>${esc(email)}</b>, a reset link is on its way. Open it in this browser.`);
      }
      if (reset) {
        const { error } = await SB.auth.updateUser({ password });
        if (error) throw error;
        toast("Password updated"); location.hash = "#/"; return;
      }
      let session;
      if (up) {
        const { data, error } = await SB.auth.signUp({ email, password, options: { data: { name }, emailRedirectTo: `${location.origin}/` } });
        if (error) throw error;
        if (data.user && Array.isArray(data.user.identities) && data.user.identities.length === 0)
          throw new Error("An account with this email already exists. Try signing in.");
        if (!data.session)
          return renderNotice("Confirm your email", `We sent a confirmation link to <b>${esc(email)}</b>. Open it in this browser to finish creating your account.`);
        session = data.session;
      } else {
        const { data, error } = await SB.auth.signInWithPassword({ email, password });
        if (error) throw error;
        session = data.session;
      }
      await syncSession(session);
      const next = lsGet("clipforge.next", null); lsSet("clipforge.next", null);
      toast(up ? `Welcome to ClipForge, ${ME.name.split(" ")[0]}!` : `Welcome back, ${ME.name.split(" ")[0]}`);
      refreshUser(); updateConnDot();
      const dest = next && !/^#\/(signin|signup|forgot|reset)?$/.test(next) ? next : "#/";
      if (location.hash === dest) route(); else location.hash = dest;
    } catch (ex) { showErr(friendlyAuthError(ex)); go.disabled = false; go.textContent = label; }
  };
}

function refreshUser() {
  const b = $("#user-btn"); if (!b) return;
  b.hidden = !ME;
  if (ME) { b.textContent = (ME.name || ME.email || "?").trim()[0].toUpperCase(); b.title = `${ME.name} · ${ME.email}`; }
}
$("#user-btn").onclick = e => showMenu(e.currentTarget, [
  { header: ME?.name || "", sub: ME?.email || "" },
  { label: "AI model settings", icon: "sparkle", run: openSettings },
  { label: "Change password", icon: "edit", run: () => { location.hash = "#/reset"; } },
  "-",
  { label: "Sign out", icon: "logout", run: signOut },
]);
async function signOut() {
  try { await SB?.auth.signOut(); } catch {}
  try { await api("/api/auth/logout", { method: "POST" }); } catch {}
  ME = null; current = null; refreshUser();
  location.hash = "#/"; route(); toast("Signed out");
}

// ================================================================ router ==
async function route() {
  clearTimeout(pollTimer);
  $("#menu").hidden = true; $("#tip").hidden = true;
  if ($("#modal").open) $("#modal").close();
  if ($("#editor").open) $("#editor").close();
  const h = location.hash || "#/";
  if (h === "#/reset" && ME) { showPublic(true); return renderAuth("reset"); }
  if (!ME) {                                   // signed out: landing + auth pages only
    showPublic(true); window.scrollTo(0, 0);
    if (h === "#/signup") return renderAuth("signup");
    if (h === "#/signin") return renderAuth("signin");
    if (h === "#/forgot") return renderAuth("forgot");
    if (!/^#\/?$/.test(h)) { if (h !== "#/reset") lsSet("clipforge.next", h); location.hash = "#/signin"; return; }
    return renderLanding();
  }
  if (/^#\/(signin|signup|forgot)$/.test(h)) { location.hash = "#/"; return; }
  showPublic(false);
  document.title = "ClipForge · viral shorts from long videos";
  const m = h.match(/^#\/p\/(\w+)/), lib = h.match(/^#\/projects(?:\/(\w+))?/);
  const section = m || lib ? "projects" : h.startsWith("#/analytics") ? "analytics" : h.startsWith("#/connections") ? "connections"
    : h.startsWith("#/billing") ? "billing" : "home";
  $$("[data-nav]").forEach(a => { const on = a.dataset.nav === section; a.classList.toggle("active", on); on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
  try {
    if (m) await renderProject(m[1]);
    else if (lib) await renderLibrary(lib[1]);
    else if (section === "analytics") await renderAnalytics();
    else if (section === "connections") await renderConnections();
    else if (section === "billing") await renderBilling();
    else await renderHome();
  } catch (e) {
    view.innerHTML = `<div class="empty"><div class="ico">${icon("alert")}</div>${esc(e.message)}<div style="margin-top:12px"><a class="btn" href="#/">Back home</a></div></div>`;
  }
  hydrateIcons(view);
}
window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
window.addEventListener("resize", () => current && location.hash.startsWith("#/p/") && $("#heat-c") && drawHeat(current));

(async () => {
  hydrateIcons();
  try { INFO = await api("/api/info"); } catch {}
  if (INFO?.supabase_url && INFO?.supabase_key && window.supabase) {
    SB = window.supabase.createClient(INFO.supabase_url, INFO.supabase_key, {
      auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
    // keep the server cookie in step with supabase-js's hourly token refresh
    SB.auth.onAuthStateChange((event, session) => {
      if (event === "TOKEN_REFRESHED" && session) setTimeout(() => syncSession(session).catch(() => {}), 0);
    });
  }
  // Links from confirmation / reset emails come back as /?code=… (PKCE). getSession() finishes the exchange.
  const params = new URLSearchParams(location.search);
  const fromEmail = params.has("code") || params.has("error_description") || params.has("error");
  let session = null;
  if (SB) { try { session = (await SB.auth.getSession()).data.session; } catch {} }
  if (session) { try { await syncSession(session); } catch { ME = null; } }
  if (fromEmail) {
    const isReset = params.has("reset");
    history.replaceState(null, "", location.pathname + (isReset && ME ? "#/reset" : location.hash || "#/"));
    if (params.get("error_description")) toast(params.get("error_description"), 6000, true);
    else if (!ME) toast(isReset ? "That reset link expired or was opened in another browser. Request a new one." : "Your email is confirmed. Sign in to continue.", 6000);
    else if (!isReset) toast(`Email confirmed. Welcome, ${ME.name.split(" ")[0]}!`);
  }
  if (params.get("checkout") === "success" && params.get("session_id")) {
    history.replaceState(null, "", location.pathname + "#/billing");
    if (ME) {
      try {
        const b = await api("/api/billing/sync", { method: "POST", body: { session_id: params.get("session_id") } });
        toast(`You're on ${b.plans.find(p => p.id === b.plan)?.name || "your new"} plan. Thanks!`, 5000);
      } catch (e) { fail(e); }
    }
  }
  refreshPill(); refreshUser();
  route();
  if (ME) updateConnDot();
})();
