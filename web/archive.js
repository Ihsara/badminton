"use strict";

/* Archive panel: private list of archived tournaments, served ONLY by the
   always-on home server (window.MAINT). No archive data is ever persisted
   client-side or committed — everything is fetched at runtime from the
   container's /api/archive/* endpoints. Access is bounded by the home server
   being local/LAN-only, not by an in-app password. */

async function viewArchive(app, id, drawId) {
  if (!window.MAINT) {
    app.innerHTML = `<div class="empty rise" style="padding:64px">
      <h1 class="section-title" style="font-size:1.6rem">Archive is off here</h1><br>
      Browsing the archived brackets is only available on the home server
      (the always-on machine). This looks like the public snapshot.<br><br>
      <a class="tag" href="#/">← back to the group</a></div>`;
    return;
  }
  // #/archive/{id}/{drawId} -> one event sub-page; #/archive/{id} -> event index;
  // #/archive -> tournament list. No password: the home server is the boundary.
  if (id && drawId) { showArchiveDraw(id, drawId); return; }
  if (id) { showArchiveTournament(id); return; }
  const list = await fetchArchiveTournaments();
  if (list === null) {
    app.innerHTML = `
      <h1 class="section-title rise" style="margin:6px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">Archive</h1>
      <div class="empty rise" style="padding:48px">
        Couldn't reach the archive on the home server.<br><br>
        <a class="tag" href="#/">← back to the group</a></div>`;
    stagger();
    return;
  }
  await ensureFriendSet();
  renderArchiveList(list);
}

// Core friend nicknames, lowercased. Fetched once per unlock from the authed
// core-names endpoint; never persisted. null = not yet fetched, Set = fetched
// (possibly empty on failure — highlight is a nice-to-have, not load-bearing).
let archFriendSet = null;

async function ensureFriendSet() {
  if (archFriendSet !== null) return;
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/core-names");
    if (!r.ok) { archFriendSet = new Set(); return; }
    const data = await r.json();
    archFriendSet = new Set((data.names || []).map((n) => n.toLowerCase()));
  } catch (_) {
    archFriendSet = new Set();
  }
}

async function fetchArchiveTournaments() {
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/tournaments");
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

async function fetchArchiveBracket(id) {
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/tournament/" +
      encodeURIComponent(id) + "/bracket");
    if (r.status === 404) return "notfound";
    if (!r.ok) return null;
    return await r.json();
  } catch (_) {
    return null;
  }
}

function archSide(slot, isWinner) {
  const names = esc((slot || []).map((p) => p.name).join(" / ") || "—");
  const isFriend = (archFriendSet || new Set()).size > 0 &&
    (slot || []).some((p) => archFriendSet.has((p.name || "").toLowerCase()));
  const cls = "slot" + (isWinner ? " slot--won" : "") + (isFriend ? " slot--friend" : "");
  return '<div class="' + cls + '">' + names + "</div>";
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

function archRenderDraw(draw, hideHeading) {
  // hideHeading: the event sub-page already shows the draw name as its <h1>.
  const head = hideHeading ? "" : "<h3>" + esc(draw.name) + "</h3>";
  const elimination = draw.matches.some((m) => m.round_index !== 99);
  if (!elimination) {
    // group/round-robin: W-L standings table
    return '<div class="draw rise">' + head + archStandingsTable(draw.matches) + "</div>";
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
  return '<div class="draw rise">' + head + '<div class="bracket">' + cols + "</div></div>";
}

// One in-memory cache of the last tournament payload, so moving between the
// event index and an event sub-page (or back) doesn't re-hit the endpoint.
let archTournamentCache = null; // { id, payload }

async function loadTournamentPayload(id) {
  if (archTournamentCache && archTournamentCache.id === id) {
    return archTournamentCache.payload;
  }
  await ensureFriendSet();
  const payload = await fetchArchiveBracket(id);
  if (payload && typeof payload === "object") archTournamentCache = { id, payload };
  return payload;
}

function archBracketError(payload) {
  // Returns HTML for the non-object payloads, or "" when the payload is real.
  const back = `<a href="#/archive" class="tag rise">← all tournaments</a>`;
  if (payload === "notfound") {
    return back + `<div class="empty rise" style="padding:48px">Tournament not found.</div>`;
  }
  if (payload === null) {
    return back + `<div class="empty rise" style="padding:48px">Couldn't load the bracket.</div>`;
  }
  return ""; // real payload
}

// A short "MS C" / "Group A" style code for the draw when its name has a suffix.
function archDrawKind(draw) {
  const ms = draw.matches || [];
  if (!ms.length) return { tag: "empty", n: 0 };
  const isGroup = ms.every((m) => m.round_index === 99);
  return { tag: isGroup ? "group" : "bracket", n: ms.length };
}

// Tournament page = the EVENT INDEX (one row per draw/topic), not every bracket
// stacked. Each event links to its own sub-page #/archive/{id}/{drawId}.
async function showArchiveTournament(id) {
  const payload = await loadTournamentPayload(id);
  const err = archBracketError(payload);
  if (err === null) return;      // auth -> password form already rendered
  if (err) { app.innerHTML = err; stagger(); return; }

  const draws = payload.draws || [];
  const index = draws.length
    ? `<section class="block rise"><ul class="arch-list">
        ${draws.map((d) => {
          const k = archDrawKind(d);
          return `<li class="arch-item">
            <a href="#/archive/${encodeURIComponent(id)}/${encodeURIComponent(d.id)}">${esc(d.name || d.id)}</a>
            <span class="muted">${k.n} match${k.n === 1 ? "" : "es"}${k.tag === "group" ? " · group" : ""}</span>
          </li>`;
        }).join("")}
      </ul></section>`
    : `<div class="empty rise" style="padding:40px">No events (draws) archived for this tournament yet.</div>`;

  app.innerHTML = `
    <a href="#/archive" class="tag rise">← all tournaments</a>
    <h1 class="section-title rise" style="margin:10px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">
      ${esc(payload.tournament.name || id)}</h1>
    <p class="pl-record rise">${draws.length} event${draws.length === 1 ? "" : "s"} — pick one to see its bracket.</p>
    ${index}`;
  stagger();
}

// Event sub-page = ONE draw's bracket/standings, reached from the event index.
async function showArchiveDraw(id, drawId) {
  const payload = await loadTournamentPayload(id);
  const err = archBracketError(payload);
  if (err === null) return;
  if (err) { app.innerHTML = err; stagger(); return; }

  const draw = (payload.draws || []).find((d) => d.id === drawId);
  const tourHref = `#/archive/${encodeURIComponent(id)}`;
  if (!draw) {
    app.innerHTML = `<a href="${tourHref}" class="tag rise">← all events</a>
      <div class="empty rise" style="padding:48px">That event wasn't found in this tournament.</div>`;
    stagger();
    return;
  }
  app.innerHTML = `
    <a href="${tourHref}" class="tag rise">← ${esc(payload.tournament.name || "all events")}</a>
    <h1 class="section-title rise" style="margin:10px 0 4px;font-size:clamp(1.5rem,4.5vw,2.2rem)">
      ${esc(draw.name || drawId)}</h1>
    ${archRenderDraw(draw, true)}`;
  stagger();
}
