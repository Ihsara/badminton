"use strict";

/* Archive panel: private, edit-password gated list of archived tournaments.
   Only reachable when app.js detected a live, writable container (window.MAINT).
   No archive data is ever persisted client-side or committed — everything is
   fetched at runtime from the container's /api/archive/* endpoints. The
   password itself is kept in sessionStorage (tab-scoped) so it survives
   re-entering the view, but that's the only thing we stash. */

function viewArchive(app) {
  if (!window.MAINT) {
    app.innerHTML = `<div class="empty rise" style="padding:64px">
      <h1 class="section-title" style="font-size:1.6rem">Archive is off here</h1><br>
      Browsing the archived brackets is only available on the home server
      (the always-on machine). This looks like the public snapshot.<br><br>
      <a class="tag" href="#/">← back to the group</a></div>`;
    return;
  }
  renderArchivePasswordForm();
}

function archPass() { return sessionStorage.getItem("archivePw") || ""; }

function renderArchivePasswordForm(msg) {
  app.innerHTML = `
    <h1 class="section-title rise" style="margin:6px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">Archive</h1>
    <p class="pl-record rise">Browse archived tournament brackets. Password-gated.</p>
    <section class="block rise"><div class="block__head"><h2 class="section-title">Edit password</h2></div>
      <div class="card m-card">
        <span class="m-lab">Shared password</span>
        <input id="arch-pass" type="password" class="m-input" placeholder="ask Chau" autocomplete="off" />
        <p class="m-hint">Stored only in this browser tab.</p>
        ${msg ? `<div class="m-out m-out--err">${esc(msg)}</div>` : ""}
        <button id="arch-go" class="m-btn">Unlock archive</button>
      </div>
    </section>`;
  stagger();
  const pass = document.getElementById("arch-pass");
  document.getElementById("arch-go").onclick = () => loadArchive(pass.value || "");
  pass.addEventListener("keydown", (e) => { if (e.key === "Enter") loadArchive(pass.value || ""); });
  pass.focus();
}

async function loadArchive(pw) {
  const list = window.MAINT
    ? await fetchArchiveTournaments(pw)
    : null;
  if (list === "auth") { renderArchivePasswordForm("Wrong edit password."); return; }
  if (list === null) { renderArchivePasswordForm("Couldn't reach the archive."); return; }
  sessionStorage.setItem("archivePw", pw);
  renderArchiveList(list);
}

async function fetchArchiveTournaments(pw) {
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/tournaments?password=" + encodeURIComponent(pw));
    if (r.status === 401 || r.status === 403) return "auth";
    if (!r.ok) return null;
    return await r.json();
  } catch (_) {
    return null;
  }
}

function renderArchiveList(tournaments) {
  if (!tournaments.length) {
    app.innerHTML = `
      <h1 class="section-title rise" style="margin:6px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">Archive</h1>
      <div class="empty rise" style="padding:48px">
        The archive is empty. Run the archive crawler to populate it.<br><br>
        <a class="tag" href="#/">← back to the group</a></div>`;
    stagger();
    return;
  }
  app.innerHTML = `
    <h1 class="section-title rise" style="margin:6px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">Archive</h1>
    <p class="pl-record rise">${tournaments.length} archived tournament${tournaments.length === 1 ? "" : "s"}.</p>
    <section class="block rise">
      <ul class="arch-list">
        ${tournaments.map((t) => `
          <li class="arch-item">
            <a href="#/archive/${encodeURIComponent(t.id)}">${esc(t.name || t.id)}</a>
            <span class="muted">${esc(t.year || "")}</span>
          </li>`).join("")}
      </ul>
    </section>`;
  stagger();
}
