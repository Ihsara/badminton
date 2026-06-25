"use strict";

const app = document.getElementById("app");
let DB = null;

/* ---------------- data helpers ---------------- */

const byName = (n) => (DB.players.find((p) => p.player === n) || null);
const playerNames = () => DB.players.map((p) => p.player);
const inTeam = (team, name) => team.some((p) => p === name);

// A match seen from `name`'s perspective, or null if they didn't play.
function perspective(m, name) {
  const onT1 = inTeam(m.team1, name);
  const onT2 = inTeam(m.team2, name);
  if (!onT1 && !onT2) return null;
  const own = onT1 ? m.team1 : m.team2;
  const opp = onT1 ? m.team2 : m.team1;
  const won = onT1 ? m.result === "WIN" : m.result === "LOSS";
  const sets = m.sets.map(([a, b]) => (onT1 ? [a, b] : [b, a]));
  const partner = own.find((p) => p !== name) || null;
  return { won, own, opp, sets, partner, m };
}

function playerMatches(name) {
  const out = [];
  for (const m of DB.matches) {
    const v = perspective(m, name);
    if (v) out.push(v);
  }
  out.sort((a, b) => (a.m.date < b.m.date ? 1 : -1));
  return out;
}

function countBy(views, keyFn) {
  const map = new Map();
  for (const v of views) {
    const k = keyFn(v);
    if (!k) continue;
    const e = map.get(k) || { name: k, games: 0, wins: 0 };
    e.games += 1;
    e.wins += v.won ? 1 : 0;
    map.set(k, e);
  }
  return [...map.values()];
}

function headToHead(a, b) {
  const vs = { games: 0, aWins: 0, bWins: 0, list: [] };
  const wth = { games: 0, wins: 0, list: [] };
  for (const m of DB.matches) {
    const va = perspective(m, a);
    if (!va) continue;
    if (inTeam(va.own, b)) {
      wth.games += 1;
      wth.wins += va.won ? 1 : 0;
      wth.list.push(va);
    } else if (inTeam(va.opp, b)) {
      vs.games += 1;
      if (va.won) vs.aWins += 1;
      else vs.bWins += 1;
      vs.list.push(va);
    }
  }
  return { vs, wth };
}

function tournamentInfo(name) {
  const ms = DB.matches.filter((m) => m.tournament === name);
  const players = new Set();
  ms.forEach((m) => [...m.team1, ...m.team2].forEach((p) => {
    if (byName(p)) players.add(p);
  }));
  const dates = ms.map((m) => m.date).filter(Boolean).sort();
  return { matches: ms, players: [...players], dates };
}

/* ---------------- rendering utils ---------------- */

const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const initials = (n) => n.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
const fmtDate = (d) => {
  if (!d) return "";
  const dt = new Date(d);
  if (isNaN(dt)) return d;
  return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" });
};
const pct = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
const stagger = () =>
  app.querySelectorAll(".rise").forEach((el, i) => (el.style.animationDelay = Math.min(i * 45, 600) + "ms"));

function matchRow(m) {
  const s1won = m.result === "WIN";
  const score = m.sets.map(([a, b]) => `${a}-${b}`).join("  ");
  const t1 = m.team1.join(" / ");
  const t2 = m.team2.join(" / ");
  return `
    <div class="match rise">
      <div class="match__date">${fmtDate(m.date)}<br><span class="tag">${esc(m.category)} ${esc(m.level)}</span></div>
      <div class="match__teams">
        <div class="team ${s1won ? "team--win" : "team--lose"}"><b>${esc(t1)}</b><span class="score">${esc(m.sets.map((s) => s[0]).join(" "))}</span></div>
        <div class="team ${s1won ? "team--lose" : "team--win"}"><b>${esc(t2)}</b><span class="score">${esc(m.sets.map((s) => s[1]).join(" "))}</span></div>
      </div>
      <div><span class="pill pill--cat">${esc(m.round || "–")}</span></div>
    </div>`;
}

// perspective match row (for a player page)
function pMatchRow(v) {
  const m = v.m;
  return `
    <div class="match rise">
      <div class="match__date">${fmtDate(m.date)}<br><span class="tag">${esc(m.category)} ${esc(m.level)}</span></div>
      <div class="match__teams">
        <div class="team ${v.won ? "team--win" : "team--lose"}"><b>${esc(v.own.join(" / "))}</b><span class="score">${esc(v.sets.map((s) => s[0]).join(" "))}</span></div>
        <div class="team ${v.won ? "team--lose" : "team--win"}"><b>${esc(v.opp.join(" / "))}</b><span class="score">${esc(v.sets.map((s) => s[1]).join(" "))}</span></div>
      </div>
      <div><span class="pill ${v.won ? "pill--cat" : "pill--cat"}">${v.won ? "WON" : "LOST"}</span></div>
    </div>`;
}

/* ---------------- views ---------------- */

function viewGroup() {
  const c = DB.counts;
  const top = DB.players.slice(0, 12);
  const recent = [...DB.matches].sort((a, b) => (a.date < b.date ? 1 : -1)).slice(0, 8);
  const maxWins = Math.max(...DB.players.map((p) => p.wins), 1);

  app.innerHTML = `
    <section class="hero">
      <div>
        <div class="eyebrow rise">Finland · ${esc(DB.tournaments_list.length)} tournaments logged</div>
        <h1 class="rise">${esc(DB.group_name).replace(" ", " <em>")}</em></h1>
        <p class="rise">A living almanac of our badminton season — every match, every score, every rivalry, pulled from tournamentsoftware and counted by hand-rolled Python.</p>
      </div>
      <div class="tiles">
        <div class="tile rise"><b>${c.players}</b><span>Players</span></div>
        <div class="tile rise"><b>${c.matches}</b><span>Matches</span></div>
        <div class="tile rise"><b>${c.tournaments}</b><span>Events</span></div>
      </div>
    </section>

    <section class="block">
      <div class="block__head"><h2 class="section-title">The Standings</h2><a class="tag" href="#/players">all players →</a></div>
      <div class="card lb">
        ${top.map((p, i) => lbRow(p, i, maxWins)).join("")}
      </div>
    </section>

    <section class="block">
      <div class="block__head"><h2 class="section-title">Latest Results</h2><a class="tag" href="#/tournaments">tournaments →</a></div>
      <div class="matches">${recent.map(matchRow).join("")}</div>
    </section>`;
  stagger();
}

function lbRow(p, i, maxWins) {
  return `
    <a class="lb__row rise ${i === 0 ? "lb__row--top" : ""}" href="#/player/${encodeURIComponent(p.player)}">
      <span class="lb__rank">${i + 1}</span>
      <span class="lb__name">${esc(p.player)} <span class="lb__sub">${p.games}g</span></span>
      <span class="bar"><i style="width:${Math.round((p.wins / maxWins) * 100)}%"></i></span>
      <span class="wl"><b>${p.wins}</b><s> / ${p.losses}</s></span>
      <span class="pct">${pct(p.win_ratio)}</span>
    </a>`;
}

function viewPlayers() {
  const maxWins = Math.max(...DB.players.map((p) => p.wins), 1);
  app.innerHTML = `
    <div class="eyebrow rise">Roster</div>
    <h1 class="section-title rise" style="margin:8px 0 24px">All Players</h1>
    <div class="card lb">${DB.players.map((p, i) => lbRow(p, i, maxWins)).join("")}</div>`;
  stagger();
}

function viewPlayer(name) {
  const p = byName(name);
  if (!p) return notFound("No player called “" + name + "”.");
  const views = playerMatches(name);

  const partners = countBy(views.filter((v) => v.partner), (v) => v.partner)
    .sort((a, b) => b.wins - a.wins || b.games - a.games)
    .slice(0, 6);
  const opponents = countBy(views.flatMap((v) => v.opp.map((o) => ({ ...v, _o: o }))), (v) => (byName(v._o) ? v._o : null))
    .filter((o) => o.name !== name)
    .sort((a, b) => b.games - a.games)
    .slice(0, 6);
  const form = views.slice(0, 10).reverse();
  const pt = DB.player_tournament.filter((r) => r.player === name).sort((a, b) => b.wins - a.wins);

  app.innerHTML = `
    <a class="tag rise" href="#/players">← roster</a>
    <section class="pl-hero" style="margin-top:16px">
      <div class="avatar rise">${esc(initials(name))}</div>
      <div>
        <h1 class="rise">${esc(name)}</h1>
        <div class="pl-record rise"><b>${p.wins}W</b> – ${p.losses}L · ${pct(p.win_ratio)} win rate · ${p.games} games</div>
        <div class="form rise">${form.map((v) => `<span class="dot dot--${v.won ? "w" : "l"}">${v.won ? "W" : "L"}</span>`).join("")}</div>
      </div>
    </section>

    <div class="statgrid">
      <div class="stat rise"><b>${p.sets_won}–${p.sets_lost}</b><span>Sets</span></div>
      <div class="stat rise"><b>${p.points_for}</b><span>Points for</span></div>
      <div class="stat rise"><b>${p.points_per_set ?? "–"}</b><span>Pts / set</span></div>
      <div class="stat rise"><b>${pct(p.third_set_ratio)}</b><span>3rd-set rate</span></div>
      <div class="stat rise"><b>${p.points_for - p.points_against >= 0 ? "+" : ""}${p.points_for - p.points_against}</b><span>Point diff</span></div>
    </div>

    <div class="cols" style="margin-top:30px">
      <section>
        <div class="block__head"><h2 class="section-title">Best Partners</h2></div>
        <div class="card list">${partners.length ? partners.map((x) => sideItem(x)).join("") : emptyMini("No doubles partners yet.")}</div>
      </section>
      <section>
        <div class="block__head"><h2 class="section-title">Played Most</h2></div>
        <div class="card list">${opponents.length ? opponents.map((x) => sideItem(x)).join("") : emptyMini("No rivals yet.")}</div>
      </section>
    </div>

    ${pt.length ? `
    <section class="block">
      <div class="block__head"><h2 class="section-title">By Tournament</h2></div>
      <div class="card list">${pt.map((r) => `
        <a class="list__item" href="#/tournament/${encodeURIComponent(r.tournament)}">
          <span class="list__name">${esc(r.tournament)}</span>
          <span class="list__num"><b>${r.wins}</b>–${r.losses} · ${pct(r.win_ratio)}</span>
        </a>`).join("")}</div>
    </section>` : ""}

    <section class="block">
      <div class="block__head"><h2 class="section-title">Match Log</h2><span class="tag">${views.length} matches</span></div>
      <div class="matches">${views.slice(0, 40).map(pMatchRow).join("")}</div>
    </section>`;
  stagger();
}

function sideItem(x) {
  return `
    <a class="list__item" href="#/player/${encodeURIComponent(x.name)}">
      <span class="avatar" style="width:34px;height:34px;font-size:0.9rem;border-radius:10px">${esc(initials(x.name))}</span>
      <span class="list__name">${esc(x.name)}</span>
      <span class="list__num"><b>${x.wins}</b>–${x.games - x.wins} <s style="color:var(--muted-2)">(${x.games})</s></span>
    </a>`;
}

function viewH2H(a, b) {
  const names = playerNames();
  a = a || names[0];
  b = b || names[1];
  const opt = (sel) => names.map((n) => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("");
  const { vs, wth } = headToHead(a, b);

  app.innerHTML = `
    <div class="eyebrow rise">The Tale of the Tape</div>
    <h1 class="section-title rise" style="margin:8px 0 26px">Head to Head</h1>
    <div class="h2h-pick rise">
      <select id="h2h-a">${opt(a)}</select>
      <span class="vs">vs</span>
      <select id="h2h-b">${opt(b)}</select>
    </div>

    <div class="card rise">
      <div class="scoreline">
        <div>
          <div class="big ${vs.aWins >= vs.bWins ? "win-side" : "lose-side"}">${vs.aWins}</div>
          <div class="nm">${esc(a)}</div>
        </div>
        <div class="dash">–</div>
        <div>
          <div class="big ${vs.bWins > vs.aWins ? "win-side" : "lose-side"}">${vs.bWins}</div>
          <div class="nm">${esc(b)}</div>
        </div>
      </div>
    </div>
    <p class="empty" style="padding:14px">${vs.games} meetings as opponents${wth.games ? ` · ${wth.wins}–${wth.games - wth.wins} as partners (${wth.games} together)` : ""}</p>

    ${vs.list.length ? `<section class="block"><div class="block__head"><h2 class="section-title">When they clashed</h2></div>
      <div class="matches">${vs.list.sort((x, y) => (x.m.date < y.m.date ? 1 : -1)).map(pMatchRow).join("")}</div></section>` : ""}
    ${wth.list.length ? `<section class="block"><div class="block__head"><h2 class="section-title">When they teamed up</h2></div>
      <div class="matches">${wth.list.sort((x, y) => (x.m.date < y.m.date ? 1 : -1)).map(pMatchRow).join("")}</div></section>` : ""}`;

  const selA = document.getElementById("h2h-a");
  const selB = document.getElementById("h2h-b");
  const go = () => (location.hash = `#/h2h/${encodeURIComponent(selA.value)}/${encodeURIComponent(selB.value)}`);
  selA.onchange = go;
  selB.onchange = go;
  stagger();
}

function viewTournaments() {
  const cards = DB.tournaments_list
    .map((t) => ({ name: t, info: tournamentInfo(t) }))
    .sort((a, b) => ((a.info.dates[0] || "") < (b.info.dates[0] || "") ? 1 : -1));
  app.innerHTML = `
    <div class="eyebrow rise">The Circuit</div>
    <h1 class="section-title rise" style="margin:8px 0 24px">Tournaments</h1>
    <div class="tgrid">${cards.map((c) => `
      <a class="card tcard rise" href="#/tournament/${encodeURIComponent(c.name)}">
        <h3>${esc(c.name)}</h3>
        <div class="tcard__stats">
          <span><b>${c.info.matches.length}</b>matches</span>
          <span><b>${c.info.players.length}</b>of us</span>
          <span style="margin-left:auto;align-self:end">${fmtDate(c.info.dates[0])}</span>
        </div>
      </a>`).join("")}</div>`;
  stagger();
}

function viewTournament(name) {
  const info = tournamentInfo(name);
  if (!info.matches.length) return notFound("No matches for “" + name + "”.");
  const ms = [...info.matches].sort((a, b) => (a.date < b.date ? 1 : -1));
  app.innerHTML = `
    <a class="tag rise" href="#/tournaments">← all tournaments</a>
    <h1 class="section-title rise" style="margin:14px 0 6px;font-size:clamp(1.8rem,5vw,2.8rem)">${esc(name)}</h1>
    <p class="pl-record rise">${info.matches.length} matches · ${info.players.length} of the crew · ${fmtDate(info.dates[0])}${info.dates.length > 1 && info.dates[info.dates.length - 1] !== info.dates[0] ? " – " + fmtDate(info.dates[info.dates.length - 1]) : ""}</p>
    <div class="block__head" style="margin-top:24px"><h2 class="section-title">Who played</h2></div>
    <div class="card lb">${info.players
      .map((n) => byName(n))
      .filter(Boolean)
      .map((p, i) => lbRow(p, i, Math.max(...DB.players.map((x) => x.wins), 1)))
      .join("")}</div>
    <section class="block"><div class="block__head"><h2 class="section-title">Every match</h2></div>
      <div class="matches">${ms.map(matchRow).join("")}</div></section>`;
  stagger();
}

function notFound(msg) {
  app.innerHTML = `<div class="empty rise" style="padding:80px">${esc(msg)}<br><br><a class="tag" href="#/">← back to the group</a></div>`;
  stagger();
}

function emptyMini(msg) {
  return `<div class="empty" style="padding:24px">${esc(msg)}</div>`;
}

/* ---------------- router ---------------- */

function router() {
  if (!DB) return;
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const [route, a, b] = parts;
  document.querySelectorAll(".nav a").forEach((el) =>
    el.classList.toggle("active", el.dataset.route === (route || "")));
  window.scrollTo({ top: 0 });
  switch (route) {
    case "": case undefined: return viewGroup();
    case "players": return viewPlayers();
    case "player": return viewPlayer(a);
    case "h2h": return viewH2H(a, b);
    case "tournaments": return viewTournaments();
    case "tournament": return viewTournament(a);
    case "maintain": return viewMaintain(app);
    default: return notFound("Unknown page.");
  }
}

/* ---------------- boot ---------------- */

const CFG = window.BADMINTON_CONFIG || {};
// API base for live data + maintenance. "" = same origin (local container).
const API_BASE = (CFG.apiBase || "").replace(/\/$/, "");
// Where the Maintain panel sends its requests once detected (see maintain.js).
window.MAINT = null;

function fetchJSON(url, timeoutMs) {
  const ctrl = new AbortController();
  const t = timeoutMs ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  return fetch(url, { signal: ctrl.signal })
    .then((r) => {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    })
    .finally(() => t && clearTimeout(t));
}

function banner(html, kind) {
  const el = document.getElementById("banner");
  if (!html) { el.hidden = true; return; }
  el.className = "banner banner--" + (kind || "info");
  el.innerHTML = html;
  el.hidden = false;
}

function setMeta() {
  document.getElementById("meta").innerHTML =
    `updated ${fmtDate(DB.generated_at)}<br>source: ${esc(DB.source)}`;
  document.getElementById("foot-meta").textContent =
    `${DB.counts.matches} matches · generated ${DB.generated_at}`;
}

// Probe the container; if reachable and writable, reveal the Maintain tab.
async function detectMaintain() {
  try {
    const h = await fetchJSON((API_BASE || "") + "/api/health", 4000);
    if (h && h.ok) {
      window.MAINT = { base: API_BASE || "", writes: !!h.writes_enabled, health: h };
      document.getElementById("nav-maintain").hidden = false;
    }
  } catch (_) { /* no container reachable — read-only site */ }
}

async function boot() {
  // 1. The published snapshot — always shipped beside this page, so the site
  //    works even when the home container is offline.
  let snap = null;
  try { snap = await fetchJSON("./data.json"); } catch (_) { /* may not exist on a bare deploy */ }

  // 2. If a remote container is configured, prefer its fresher live data.
  let live = null, liveTried = false;
  if (API_BASE) {
    liveTried = true;
    try { live = await fetchJSON(API_BASE + "/data.json", 4000); } catch (_) { /* offline */ }
  }

  DB = live || snap;
  if (!DB) {
    app.innerHTML = `<div class="empty" style="padding:80px">Couldn't load the data.<br><br>
      If you opened the file directly, run <code>uv run badminton server</code> and open the served URL instead —
      browsers block <code>fetch</code> from <code>file://</code>.</div>`;
    return;
  }

  setMeta();
  if (liveTried && !live && snap) {
    banner(`<b>Live data is offline.</b> Showing the last published snapshot from
      ${esc(fmtDate(snap.generated_at))}. Ping Chau if it looks stale.`, "warn");
  } else if (live) {
    banner("", null);
  }

  window.addEventListener("hashchange", router);
  await detectMaintain();
  router();
}

boot();
