"use strict";

const PCOLORS = ["#4f86c6", "#c9534f", "#5d9b62", "#8a63b5", "#d9a22e"];
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const ORD = ["1st", "2nd", "3rd", "4th", "5th"];

let me, mine = [], board, tab = "mine";
let photo;  // in the profile dialog: undefined = unchanged, a Blob = new picture, null = remove it
const choice = { opponents: 1, scoring: "green" };

async function api(path, body) {
  const init = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, init);
  if (!r.ok) throw Object.assign(new Error(`${path}: ${r.status}`), { status: r.status });
  return r.json();
}

const play = (id) => location.assign(`/game.html?g=${id}`);

function when(iso) {
  const d = new Date(iso), days = Math.floor((Date.now() - d) / 864e5);
  if (days === 0) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (days < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

const chip = (name, i) => `<span class="who" style="--pc:${PCOLORS[i]}">${esc(name)}</span>`;
const person = (p, i, name = p.name) => `<span class="who person" style="--pc:${PCOLORS[i]}">${avatarHtml(p, PCOLORS[i], "xs")}${esc(name)}</span>`;
const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
const num = (x) => (x == null ? "–" : Math.round(x));

// =============================================================================
// Header, hero scoreboard, new game
// =============================================================================

function renderMe() {
  $("#me").innerHTML = `<button class="ghost small" data-click="report">Report a bug</button><span class="m-signed">Playing as</span>
    <button class="ghost me-btn" data-click="rename">${avatarHtml(me, PCOLORS[0], "sm")}${esc(me.name || "…")} ✎</button>`;
}

// Humans vs AI, front and center: the score, the champion to beat, and the way into a game.
function renderHero() {
  const t = board.humans_vs_ai.all, c = board.humans_vs_ai.champion;
  const lead = t.humans > t.ai ? "Humans lead" : t.ai > t.humans ? "The machines lead" : t.humans ? "Dead even" : "No games yet: be the first";
  const current = mine.find((g) => g.status === "in_progress");
  $("#hero").innerHTML = `<div class="hero-text">
      <div class="hero-kicker">Humans vs AI</div>
      <div class="vs-big">
        <div class="side h"><b>${t.humans}</b><span>Humans</span></div>
        <span class="dash">–</span>
        <div class="side a"><b>${t.ai}</b><span>AI</span></div>
      </div>
      <div class="hero-lead">${lead}${t.draws ? ` · ${t.draws} draw${t.draws > 1 ? "s" : ""}` : ""}</div>
      <div class="hero-champ">${avatarHtml(me.bot, PCOLORS[1], "xl")}
        <div><div class="hero-kicker">${me.bot.champion ? "Current champion" : "Opponent"}</div>
          <div class="champ-name">${esc(me.bot.name)}</div>
          ${me.bot.champion && c.humans + c.ai + c.draws ? `<div class="champ-rec">Humans ${c.humans} – ${c.ai} against it</div>` : ""}</div></div>
      <div class="hero-actions">
        ${current ? `<button class="primary" data-click="play:${current.id}">Continue game · round ${current.round}</button>` : ""}
        <button class="${current ? "ghost" : "primary"}" data-click="new">New game</button>
      </div>
    </div>
    <img class="hero-img" src="robot-wingspan.webp" alt="" draggable="false">`;
}

function newGameDialog() {
  const seg = (key, options) =>
    `<div class="seg">${options.map(([v, label]) => `<button class="${choice[key] === v ? "on" : ""}" data-click="choose:${key}:${v}">${label}</button>`).join("")}</div>`;
  const m = $("#modal");
  m.innerHTML = `<div class="sheet name-sheet"><h2>New game</h2>
    <p>You'll face <b>${esc(me.bot.name)}</b>${me.bot.champion ? ", the current champion" : ""}.</p>
    <div class="ng-row"><span>Opponents</span>${seg("opponents", [1, 2, 3, 4].map((n) => [n, n]))}</div>
    <div class="ng-row"><span>Goal board</span>${seg("scoring", [["green", "Green"], ["blue", "Blue"]])}</div>
    <div class="m-foot"><button class="ghost" data-click="close">Cancel</button><button class="primary" data-click="start">Start game</button></div></div>`;
  m.hidden = false;
}

// =============================================================================
// Tabs: games and leaderboard
// =============================================================================

function gameRow(g, perspective) {
  const seats = g.seats.map((s, i) => person(s, i, s.kind === "human" && s.uid === me.uid ? "You" : s.name)).join("");
  let status;
  if (g.status === "finished") {
    const i = perspective ? g.seats.findIndex((s) => s.uid === me.uid) : g.result.findIndex((r) => r.place === 1);
    const r = g.result[i], shared = g.result.filter((x) => x.place === r.place).length > 1;
    const scores = g.result.map((x) => x.score).join(" – ");
    status = perspective
      ? `<b class="${r.place === 1 && !shared ? "won" : ""}">${shared ? "Tied " : ""}${ORD[r.place - 1]}</b> · ${scores}`
      : `${shared ? "Draw" : `${chip(g.seats[i].name, i)} won`} · ${scores}`;
  } else {
    status = g.abandoned ? `<span class="muted">Abandoned in round ${g.round}</span>` : `In progress · round ${g.round} of 4`;
  }
  const mineToPlay = g.status === "in_progress" && g.seats.some((s) => s.uid === me.uid);
  return `<tr data-click="play:${g.id}"><td class="muted">${when(g.updated)}</td><td>${seats}</td>
    <td><span class="board-dot ${g.scoring}"></span></td><td>${status}</td>
    <td class="go">${mineToPlay ? "Play →" : "View →"}</td></tr>`;
}

function gamesTable(games, perspective) {
  if (!games.length) return `<p class="muted empty-tab">No games yet.</p>`;
  return `<table class="list"><tr><th>When</th><th>Players</th><th>Board</th><th>Result</th><th></th></tr>
    ${games.map((g) => gameRow(g, perspective)).join("")}</table>`;
}

function boardHtml(b) {
  const players = b.players.map((p, k) => `<tr><td>${k + 1}</td><td class="lb-who">${avatarHtml(p, PCOLORS[0], "sm")}${esc(p.name)}</td><td>${p.games}</td><td>${p.wins}</td>
    <td>${pct(p.win_rate)}</td><td>${num(p.avg_score)}</td><td>${p.best_score ?? "–"}</td><td class="muted">${p.abandoned || ""}</td></tr>`).join("");
  const bots = b.bots.map((p) => `<tr><td class="lb-who">${avatarHtml(p, PCOLORS[1], "sm")}${esc(p.name)}${p.name === b.champion ? ' <span class="champ">champion</span>' : ""}</td>
    <td>${p.games}</td><td>${p.wins}</td><td>${pct(p.win_rate)}</td><td>${num(p.avg_score)}</td></tr>`).join("");
  const rec = b.records;
  return `<h3 class="lb-title">Leaderboard</h3>
    <div class="records">
      ${rec.high_score ? `<span>Highest score: <b>${rec.high_score.score}</b> by ${esc(rec.high_score.name)}</span>` : ""}
      ${rec.biggest_win ? `<span>Biggest win: <b>+${rec.biggest_win.margin}</b> by ${esc(rec.biggest_win.name)}</span>` : ""}
    </div>
    <h4>Players</h4>
    ${players ? `<table class="list"><tr><th>#</th><th>Player</th><th>Games</th><th>Wins</th><th>Win %</th><th>Avg</th><th>Best</th><th title="unfinished for 7+ days">Abandoned</th></tr>${players}</table>` : '<p class="muted">No finished games yet.</p>'}
    <h4>AI releases</h4>
    ${bots ? `<table class="list"><tr><th>Bot</th><th>Games</th><th>Wins vs humans</th><th>Win %</th><th>Avg</th></tr>${bots}</table>` : '<p class="muted">No finished games yet.</p>'}`;
}

async function renderTab() {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  $("#tab").innerHTML = tab === "mine" ? gamesTable(mine, true) : gamesTable(await api("/api/games?scope=all"), false);
}

// =============================================================================
// Name
// =============================================================================

function askProfile(required) {
  photo = undefined;
  const m = $("#modal");
  m.innerHTML = `<div class="sheet name-sheet"><h2>${required ? "Welcome!" : "Your profile"}</h2>
    <p>How should other players see you on the leaderboard?</p>
    <form id="name-form">
      <div class="pf-row"><div id="pf-preview"></div>
        <input id="name-input" maxlength="20" value="${esc(me.name || "")}" placeholder="Your name" autofocus></div>
      <div class="pf-photo"><label class="ghost small">Upload picture<input type="file" id="photo-input" accept="image/*" hidden></label>
        <button type="button" class="ghost small" data-click="no-photo" id="no-photo">Remove</button>
        <span class="muted">optional</span></div>
      <p class="err" id="name-err"></p>
      <div class="m-foot">${required ? "<div></div>" : '<button type="button" class="ghost" data-click="close">Cancel</button>'}
      <button class="primary" type="submit">Save</button></div></form></div>`;
  m.hidden = false;
  renderPreview();
  $("#name-input").focus();
}

function renderPreview() {
  const shown = photo === undefined ? me.avatar : photo && URL.createObjectURL(photo);
  $("#pf-preview").innerHTML = avatarHtml({ avatar: shown, name: $("#name-input")?.value || me.name }, PCOLORS[0], "lg");
  $("#no-photo").hidden = !shown;
}

// Crop to a centered square and shrink before uploading (the server re-encodes it anyway).
async function shrink(file) {
  const img = await createImageBitmap(file);
  const side = Math.min(img.width, img.height), size = Math.min(512, side);
  const canvas = Object.assign(document.createElement("canvas"), { width: size, height: size });
  canvas.getContext("2d").drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, size, size);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
}

document.addEventListener("input", (e) => e.target.id === "name-input" && renderPreview());

document.addEventListener("change", async (e) => {
  if (e.target.id !== "photo-input" || !e.target.files[0]) return;
  try {
    photo = await shrink(e.target.files[0]);
    $("#name-err").textContent = "";
  } catch {
    $("#name-err").textContent = "That file isn't a picture we can read.";
  }
  renderPreview();
});

document.addEventListener("submit", async (e) => {
  if (e.target.id !== "name-form") return;
  e.preventDefault();
  const name = $("#name-input").value.trim();
  if (!/^[\p{L}\p{N}_ .-]{1,20}$/u.test(name)) {
    $("#name-err").textContent = "Use letters, numbers, spaces, dots or dashes (up to 20).";
    return;
  }
  me = await api("/api/me", { name });
  if (photo) {
    const r = await fetch("/api/me/avatar", { method: "POST", headers: { "Content-Type": photo.type }, body: photo });
    if (!r.ok) {
      $("#name-err").textContent = "Couldn't save that picture; try another one.";
      return;
    }
    me = await r.json();
  } else if (photo === null) {
    me = await (await fetch("/api/me/avatar", { method: "DELETE" })).json();
  }
  $("#modal").hidden = true;
  board = await api("/api/leaderboard");  // shows the new name/picture
  render();
});

// =============================================================================

document.addEventListener("click", async (e) => {
  const tabBtn = e.target.closest("[data-tab]");
  if (tabBtn) {
    tab = tabBtn.dataset.tab;
    return renderTab();
  }
  const el = e.target.closest("[data-click]");
  if (!el) return;
  const [kind, a, b] = el.dataset.click.split(":");
  switch (kind) {
    case "play": return play(a);
    case "new": return newGameDialog();
    case "choose": choice[a] = a === "opponents" ? Number(b) : b; return newGameDialog();
    case "start": {
      el.disabled = true;
      const g = await api("/api/games", choice);
      return play(g.id);
    }
    case "report": return openReport();
    case "rename": return askProfile(false);
    case "no-photo": photo = null; return renderPreview();
    case "close": $("#modal").hidden = true; return;
  }
});

function render() {
  renderMe();
  renderHero();
  $("#leaderboard").innerHTML = boardHtml(board);
  renderTab();
}

(async () => {
  // Old game links were /?g=<id>
  const g = new URLSearchParams(location.search).get("g");
  if (g) return location.replace(`/game.html?g=${g}`);
  [me, mine, board] = await Promise.all([api("/api/me"), api("/api/games"), api("/api/leaderboard")]);
  render();
  if (!me.name) askProfile(true);  // first visit
})();
