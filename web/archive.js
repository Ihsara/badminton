"use strict";

/* Archive panel: private, edit-password gated list of archived tournaments.
   Only reachable when app.js detected a live, writable container (window.MAINT).
   No archive data is ever persisted client-side or committed — everything is
   fetched at runtime from the container's /api/archive/* endpoints. The
   password itself is kept in sessionStorage (tab-scoped) so it survives
   re-entering the view, but that's the only thing we stash. */

function viewArchive(app, id) {
  if (!window.MAINT) {
    app.innerHTML = `<div class="empty rise" style="padding:64px">
      <h1 class="section-title" style="font-size:1.6rem">Archive is off here</h1><br>
      Browsing the archived brackets is only available on the home server
      (the always-on machine). This looks like the public snapshot.<br><br>
      <a class="tag" href="#/">← back to the group</a></div>`;
    return;
  }
  if (id) { showArchiveTournament(id); return; }
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

/* ---- bracket detail (#/archive/{id}) ---- */

async function fetchArchiveBracket(id, pw) {
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/tournament/" +
      encodeURIComponent(id) + "/bracket?password=" + encodeURIComponent(pw));
    if (r.status === 401 || r.status === 403) return "auth";
    if (r.status === 404) return "notfound";
    if (!r.ok) return null;
    return await r.json();
  } catch (_) {
    return null;
  }
}

function archSide(slot, isWinner) {
  const names = esc((slot || []).map((p) => p.name).join(" / ") || "—");
  return '<div class="slot' + (isWinner ? " slot--won" : "") + '">' + names + "</div>";
}

// small muted subtext, ONLY when present
function archCourtTime(m) {
  const bits = [m.court, m.scheduled_iso].filter(Boolean).map(esc);
  return bits.length ? '<div class="match__when">' + bits.join(" · ") + "</div>" : "";
}

function archMatchBox(m) {
  // walkover / unplayed marker when nobody won
  const unplayed = (m.winner_side !== 1 && m.winner_side !== 2)
    ? '<div class="match__wo">—</div>' : "";
  return '<div class="match">' +
    archSide(m.side1, m.winner_side === 1) +
    archSide(m.side2, m.winner_side === 2) +
    '<div class="match__score">' + esc(m.score_raw || "") + "</div>" +
    unplayed + archCourtTime(m) + "</div>";
}

// group/round-robin standings (round_index == 99): Played/Won/Lost per pair,
// sorted by wins desc then losses asc, from winner_side alone.
function archStandingsTable(matches) {
  const rows = {}; // key -> {name, p, w, l}
  const keyOf = (slot) => (slot || []).map((x) => x.name).join(" / ") || "—";
  const bump = (slot, won) => {
    const k = keyOf(slot);
    const r = (rows[k] ||= { name: k, p: 0, w: 0, l: 0 });
    r.p += 1;
    if (won === true) r.w += 1;
    else if (won === false) r.l += 1; // null winner => played, neither W nor L
  };
  matches.forEach((m) => {
    const w1 = m.winner_side === 1 ? true : m.winner_side === 2 ? false : null;
    const w2 = m.winner_side === 2 ? true : m.winner_side === 1 ? false : null;
    bump(m.side1, w1);
    bump(m.side2, w2);
  });
  const sorted = Object.values(rows).sort((a, b) => b.w - a.w || a.l - b.l);
  return '<table class="standings"><thead><tr><th>Player</th><th>P</th><th>W</th>' +
    "<th>L</th></tr></thead><tbody>" +
    sorted.map((r) => "<tr><td>" + esc(r.name) + "</td><td>" + r.p + "</td><td>" +
      r.w + "</td><td>" + r.l + "</td></tr>").join("") +
    "</tbody></table>";
}

function archRenderDraw(draw) {
  const elimination = draw.matches.some((m) => m.round_index !== 99);
  if (!elimination) {
    // group/round-robin: W-L standings table
    return '<div class="draw rise"><h3>' + esc(draw.name) + "</h3>" +
      archStandingsTable(draw.matches) + "</div>";
  }
  // group matches by round_index; columns ordered earliest->Final (desc index -> leftmost)
  const byRound = {};
  draw.matches.forEach((m) => { (byRound[m.round_index] ||= []).push(m); });
  const indices = Object.keys(byRound).map(Number).sort((a, b) => b - a); // big->0
  const cols = indices.map((idx) => {
    const ms = byRound[idx].sort((a, b) => a.position - b.position);
    const label = esc(ms[0].round_label || ("Round " + idx));
    return '<div class="round"><div class="round__title">' + label + "</div>" +
      ms.map(archMatchBox).join("") + "</div>";
  }).join("");
  return '<div class="draw rise"><h3>' + esc(draw.name) + '</h3><div class="bracket">' + cols + "</div></div>";
}

async function showArchiveTournament(id) {
  const pw = archPass();
  const payload = await fetchArchiveBracket(id, pw);
  if (payload === "auth") { renderArchivePasswordForm("Wrong edit password."); return; }
  if (payload === "notfound") {
    app.innerHTML = `<a href="#/archive" class="tag">← all tournaments</a>
      <div class="empty rise" style="padding:48px">Tournament not found.</div>`;
    stagger();
    return;
  }
  if (payload === null) {
    app.innerHTML = `<a href="#/archive" class="tag">← all tournaments</a>
      <div class="empty rise" style="padding:48px">Couldn't load the bracket.</div>`;
    stagger();
    return;
  }
  app.innerHTML = `
    <a href="#/archive" class="tag rise">← all tournaments</a>
    <h1 class="section-title rise" style="margin:10px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">
      ${esc(payload.tournament.name || id)}</h1>
    ${payload.draws.map(archRenderDraw).join("")}`;
  stagger();
}
