"use strict";

/* Maintainer panel: Excel upload + nickname editor.
   Only reachable when app.js detected a live, writable container (window.MAINT).
   Talks to the same API the container exposes; every save is validated and
   git-committed server-side. */

function maintLabel(html) {
  return `<span class="m-lab">${html}</span>`;
}

function viewMaintain(app) {
  if (!window.MAINT) {
    app.innerHTML = `<div class="empty rise" style="padding:64px">
      <h1 class="section-title" style="font-size:1.6rem">Maintenance is off here</h1><br>
      Uploading the Excel and editing nicknames is only available on the home server
      (the always-on machine). This looks like the public snapshot.<br><br>
      <a class="tag" href="#/">← back to the group</a></div>`;
    return;
  }
  const writes = window.MAINT.writes;
  app.innerHTML = `
    <h1 class="section-title rise" style="margin:6px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">Maintain</h1>
    <p class="pl-record rise">Update the match log or fix nicknames. Every change is saved with full history.</p>
    ${writes ? "" : `<div class="banner banner--warn" style="position:static;margin:14px 0">
      Writing is disabled on this server (no edit password configured). Set
      <code>BADMINTON_EDIT_PASSWORD</code> and restart to enable.</div>`}

    <section class="block rise"><div class="block__head"><h2 class="section-title">Edit password</h2></div>
      <div class="card m-card">
        ${maintLabel("Shared password")}
        <input id="m-pass" type="password" class="m-input" placeholder="ask Chau" autocomplete="off" />
        <p class="m-hint">Used for both actions below. Stored only in this browser tab.</p>
      </div>
    </section>

    <section class="block rise"><div class="block__head"><h2 class="section-title">Replace the match log (Excel)</h2></div>
      <div class="card m-card">
        ${maintLabel("Your name")}
        <input id="up-who" class="m-input" placeholder="e.g. Santeri" autocomplete="off" />
        ${maintLabel("Workbook (.xlsx)")}
        <input id="up-file" type="file" accept=".xlsx" class="m-input" />
        <p class="m-hint">Must keep the <b>Data</b> sheet and its columns. Checked before anything is saved.</p>
        <button id="up-go" class="m-btn"${writes ? "" : " disabled"}>Upload &amp; commit</button>
        <div id="up-out" class="m-out"></div>
      </div>
    </section>

    <section class="block rise"><div class="block__head"><h2 class="section-title">Nicknames</h2>
      <input id="nick-search" class="m-input m-search" placeholder="filter names…" /></div>
      <div class="card m-card">
        ${maintLabel("Your name")}
        <input id="nick-who" class="m-input" placeholder="e.g. Chau" autocomplete="off" />
        <div id="nick-table" class="m-table">loading…</div>
        <div class="m-row-add"><button id="nick-add" class="m-btn m-btn--ghost">+ add a name</button></div>
        <button id="nick-go" class="m-btn"${writes ? "" : " disabled"}>Save nicknames &amp; commit</button>
        <div id="nick-out" class="m-out"></div>
      </div>
    </section>`;
  stagger();

  document.getElementById("up-go").onclick = doUpload;
  document.getElementById("nick-go").onclick = saveNicknames;
  document.getElementById("nick-add").onclick = () => addNickRow();
  document.getElementById("nick-search").oninput = (e) => filterNicks(e.target.value);
  loadNicknames();
}

function mPass() { return (document.getElementById("m-pass") || {}).value || ""; }
function api(path) { return window.MAINT.base + path; }

async function doUpload() {
  const out = document.getElementById("up-out");
  const file = document.getElementById("up-file").files[0];
  if (!file) { out.className = "m-out m-out--err"; out.textContent = "Pick an .xlsx file first."; return; }
  const fd = new FormData();
  fd.append("file", file);
  fd.append("password", mPass());
  fd.append("who", document.getElementById("up-who").value || "");
  out.className = "m-out"; out.textContent = "Validating & uploading…";
  try {
    const r = await fetch(api("/api/upload-excel"), { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok || !d.ok) { out.className = "m-out m-out--err"; out.innerHTML = errs(d, r.status); return; }
    out.className = "m-out m-out--ok";
    out.innerHTML = `Saved ✓ ${d.matches} matches · commit <code>${esc(d.committed || "—")}</code>.
      ${d.diff ? `<details class="m-diff"><summary>what changed</summary><pre>${esc(d.diff)}</pre></details>` : ""}
      <p class="m-hint">Reloading the explorer…</p>`;
    setTimeout(() => location.reload(), 1400);
  } catch (e) {
    out.className = "m-out m-out--err"; out.textContent = "Network error: " + e;
  }
}

let NICKS = [];
async function loadNicknames() {
  const el = document.getElementById("nick-table");
  try {
    const d = await fetchJSON(api("/api/nicknames"), 6000);
    NICKS = d.rows || [];
    renderNicks();
  } catch (e) {
    el.innerHTML = `<div class="m-out m-out--err">Couldn't load names: ${esc(String(e))}</div>`;
  }
}

function renderNicks() {
  const el = document.getElementById("nick-table");
  el.innerHTML = `
    <div class="m-th"><span>Name in the log</span><span>Nickname to show</span><span>Notes</span></div>
    ${NICKS.map((r, i) => `
      <div class="m-tr" data-name="${esc((r.name || "").toLowerCase())}">
        <input class="m-input m-cell" value="${esc(r.name)}" data-i="${i}" data-k="name"
               ${r.name ? "readonly" : ""} placeholder="exact name in log" />
        <input class="m-input m-cell" value="${esc(r.display)}" data-i="${i}" data-k="display" placeholder="(leave blank = unchanged)" />
        <input class="m-input m-cell" value="${esc(r.notes)}" data-i="${i}" data-k="notes" />
      </div>`).join("")}`;
  el.querySelectorAll("input.m-cell").forEach((inp) => {
    inp.oninput = () => { NICKS[+inp.dataset.i][inp.dataset.k] = inp.value; };
  });
}

function addNickRow() {
  NICKS.push({ name: "", display: "", notes: "" });
  renderNicks();
  const rows = document.querySelectorAll("#nick-table .m-tr");
  const last = rows[rows.length - 1];
  if (last) last.querySelector("input").focus();
}

function filterNicks(q) {
  q = (q || "").toLowerCase();
  document.querySelectorAll("#nick-table .m-tr").forEach((tr) => {
    tr.style.display = !q || tr.dataset.name.includes(q) ? "" : "none";
  });
}

async function saveNicknames() {
  const out = document.getElementById("nick-out");
  out.className = "m-out"; out.textContent = "Saving…";
  const body = {
    password: mPass(),
    who: document.getElementById("nick-who").value || "",
    rows: NICKS.filter((r) => (r.name || "").trim()),
  };
  try {
    const r = await fetch(api("/api/nicknames"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok || !d.ok) { out.className = "m-out m-out--err"; out.innerHTML = errs(d, r.status); return; }
    out.className = "m-out m-out--ok";
    out.innerHTML = `Saved ✓ ${d.rows} names · commit <code>${esc(d.committed || "—")}</code>. Reloading…`;
    setTimeout(() => location.reload(), 1200);
  } catch (e) {
    out.className = "m-out m-out--err"; out.textContent = "Network error: " + e;
  }
}

function errs(d, status) {
  if (d && Array.isArray(d.errors)) return d.errors.map((e) => `• ${esc(e)}`).join("<br>");
  if (status === 401) return "Wrong edit password.";
  if (status === 403) return "Editing is disabled on this server.";
  return "Something went wrong (HTTP " + status + ").";
}
