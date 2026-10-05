"use strict";

const HAB = ["forest", "grassland", "wetland"];
const FOODS = ["invertebrate", "seed", "fish", "fruit", "rodent"];
const ROW = {
  forest: { action: "gain_food", label: "Gain food", res: "die", trade: "[card] → +1[die]" },
  grassland: { action: "lay_eggs", label: "Lay eggs", res: "egg", trade: "[wild] → +1[egg]" },
  wetland: { action: "draw_cards", label: "Draw cards", res: "card", trade: "[egg] → +1[card]" },
};
const AMOUNTS = [[1, 1, 2, 2, 3], [2, 2, 3, 3, 4], [1, 1, 2, 2, 3]];
const EXTRA = [false, true, false, true, true];
const EGG_COST = [0, 1, 1, 2, 2];
const PCOLORS = ["#4f86c6", "#c9534f", "#5d9b62", "#8a63b5", "#d9a22e"];
const EGG_TONES = ["#dfe9f3", "#f3e0df", "#e6efd8", "#f4ead0", "#ece0f0", "#fff6e0"];
// Green goal board: points for 1st/2nd/3rd per round (4th+ and players with none score 0)
const GREEN_TABLE = [[4, 1, 0], [5, 2, 1], [6, 3, 2], [7, 4, 3]];
const ORD = ["1st", "2nd", "3rd", "4th", "5th"];
// IdAction types whose id is a bird card (clickable wherever that bird is shown)
const BIRD_ID = new Set(["discard_card", "discard_bird", "discard_egg", "discard_egg_from", "select_bird", "tuck_card", "select_card"]);

let C, S, busy = false, targets = {};
const ui = { view: 0, sel: null, eggs: {}, draw: { tray: [], deck: 0 }, init: { birds: [], bonus: null, food: {} }, discard: null, showScores: true };

const $ = (s) => document.querySelector(s);
const bird = (id) => C.birds[id];
const sum = (xs) => xs.reduce((a, b) => a + b, 0);
const has = (t) => S.actions.some((a) => a.t === t);
const human = () => S.players[S.human];

// =============================================================================
// Server
// =============================================================================

async function api(path, body) {
  const init = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, init);
  if (!r.ok) throw Object.assign(new Error(`${path}: ${r.status}`), { status: r.status });
  return r.json();
}

async function call(path, body) {
  if (busy) return;
  busy = true;
  try {
    // Reload the game state instead of failing when the view is stale (409: the game moved on, e.g.
    // in another tab) or the network dropped (unknown whether the server applied the request).
    set(await api(path, body).catch((e) => {
      if (e.status && e.status !== 409) throw e;
      toast(e.status ? "The game moved on in another tab — synced to the latest state" : "Connection hiccup — reloaded the latest state");
      return api(gameUrl(""));
    }));
  } catch (e) {
    // Games live in server memory: a restart (or a long idle) forgets them.
    const msg = e.status === 404 ? "This game no longer exists on the server." : `Server error (${e.message}).`;
    const m = $("#modal");
    m.innerHTML = `<div class="sheet"><h2>Something went wrong</h2><p class="err">${msg}</p>
      <div class="m-foot"><div></div><button class="primary" data-click="new">New game</button></div></div>`;
    m.hidden = false;
  } finally {
    busy = false;
  }
}

let toastTimer;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3500);
}

// The game id lives in the URL (?g=<id>) so a reload or a bookmark resumes the same game.
const gameUrl = (path) => `/api/games/${new URLSearchParams(location.search).get("g")}${path}`;
const act = (i) => call(gameUrl("/act"), { index: i, version: S.version });

async function newGame() {
  const state = await api("/api/games", {});
  history.replaceState(null, "", `?g=${state.id}`);
  return state;
}

function set(state) {
  const waited = !S || !S.actions.length;
  S = state;
  ui.sel = null;
  ui.eggs = {};
  ui.draw = { tray: [], deck: 0 };
  if (S.phase !== "select_initial_cards") ui.init = { birds: [], bonus: null, food: {} };
  if (S.actions.length && waited) ui.view = S.human;
  targets = {};
  S.actions.forEach((a) => {
    const k = keyOf(a);
    if (k && !(k in targets)) targets[k] = a.i;
  });
  // The food picked on the setup screen answers the engine's follow-up discard step.
  if (S.phase === "discard_food" && ui.discard && S.actions.length) {
    const want = ui.discard;
    ui.discard = null;
    const a = S.actions.find((a) => FOODS.every((f) => (itemsMap(a)[f] || 0) === (want[f] || 0)));
    if (a) return setTimeout(() => act(a.i));
  }
  render();
  if (!S.game_over && !S.actions.length) setTimeout(() => call(gameUrl("/step"), {}), 450);
}

function keyOf(a) {
  switch (a.t) {
    case "SimpleAction": return `s:${a.type}`;
    case "SelectDieAction": return `die:${a.die_index}:${a.food_type}`;
    case "IdAction": return BIRD_ID.has(a.type) ? `bird:${a.id}` : null;
    case "NameAction":
      if (a.type === "select_habitat") return `hab:${a.name}`;
      if (a.type.startsWith("discard")) return `food:${a.name}`;
  }
  return null;
}
const hot = (k) => (k in targets ? "hot" : "");

// =============================================================================
// Builders for compound actions (eggs, card draws, bird placement)
// =============================================================================

const itemsMap = (a) => Object.fromEntries(a.items.map(([k, v]) => [String(k), v]));
const eggActs = () => S.actions.filter((a) => a.t === "EggMapAction").map((a) => ({ a, m: itemsMap(a) }));
const covers = (m, cand) => Object.entries(cand).every(([k, v]) => (m[k] || 0) >= v);

function eggCan(id) {
  const cand = { ...ui.eggs, [id]: (ui.eggs[id] || 0) + 1 };
  return eggActs().some(({ m }) => covers(m, cand));
}

function eggAdd(id) {
  if (!eggCan(id)) return;
  ui.eggs = { ...ui.eggs, [id]: (ui.eggs[id] || 0) + 1 };
  const n = sum(Object.values(ui.eggs));
  const fits = eggActs().filter(({ m }) => covers(m, ui.eggs));
  const exact = fits.find(({ m }) => sum(Object.values(m)) === n);
  if (exact && fits.every(({ m }) => sum(Object.values(m)) === n)) return act(exact.a.i);
  render();
}

const drawActs = () => S.actions.filter((a) => a.t === "DrawCardsAction");
const drawFits = (d) => drawActs().filter((a) => d.tray.every((b) => a.tray_birds.includes(b)) && a.deck_count >= d.deck);

function drawTry(d) {
  const fits = drawFits(d);
  if (!fits.length) return;
  ui.draw = d;
  const n = d.tray.length + d.deck;
  const exact = fits.find((a) => a.tray_birds.length + a.deck_count === n);
  if (exact && fits.every((a) => a.tray_birds.length + a.deck_count === n)) return act(exact.i);
  render();
}

function drawToggle(id) {
  const tray = ui.draw.tray.includes(id) ? ui.draw.tray.filter((b) => b !== id) : [...ui.draw.tray, id];
  drawTry({ ...ui.draw, tray });
}

const playActs = () => S.actions.filter((a) => a.t === "PlayBirdAction");
const playSpot = (r, c) => playActs().find((a) => a.bird_id === ui.sel && a.row === r && a.col === c);

function initAction() {
  const kept = [...ui.init.birds].sort((a, b) => a - b).join();
  return S.actions.find(
    (a) => a.t === "SelectInitialAction" && a.kept_bonus === ui.init.bonus && [...a.kept_birds].sort((x, y) => x - y).join() === kept
  );
}

// =============================================================================
// Components
// =============================================================================

function costHtml(b) {
  return b.cost
    .map((alt) => alt.flatMap(([f, n]) => Array(n).fill(icon(f))).join('<i class="op">+</i>'))
    .join('<i class="op">/</i>');
}

function cardHtml(id, o = {}) {
  const b = bird(id), st = o.state, p = b.power;
  const eggs = Array.from({ length: b.eggs }, (_, k) =>
    st && k < st.eggs ? `<i class="egg laid" style="--egg:${EGG_TONES[(id + k) % EGG_TONES.length]}"></i>` : `<i class="egg"></i>`
  ).join("");
  const pending = o.pending ? `<span class="c-pending">+${o.pending}${icon("egg")}</span>` : "";
  return `<div class="card ${o.cls || ""}" data-bird="${id}" ${o.attrs || ""}>
    <div class="c-tab"><div class="c-habs">${b.habitats.map(icon).join("")}</div><div class="c-cost">${costHtml(b)}</div></div>
    <div class="c-name"><span style="font-size:${b.name.length > 18 ? 6.4 : b.name.length > 13 ? 7.4 : 8.4}cqw">${b.name}</span></div>
    <div class="c-stats">
      <div class="c-pts">${b.points}${icon("points")}</div>
      <div class="c-nest" title="${b.nest} nest">${b.nest === "none" ? "" : icon(b.nest === "wild" ? "star" : b.nest)}</div>
      <div class="c-eggs">${eggs}</div>
    </div>
    <div class="c-art">${silhouetteFor(b)}</div>
    <div class="c-wing">${b.wingspan}cm</div>
    <div class="c-power ${p ? p.color : "none"}">${p ? `<div><b>${p.trigger}:</b> ${tok(p.text)}</div>` : ""}</div>
    ${st && st.cached ? `<span class="c-cache" title="cached food">${st.cached}</span>` : ""}
    ${st && st.tucked ? `<span class="c-tuck" title="tucked cards">${icon("card")}${st.tucked}</span>` : ""}
    ${pending}
  </div>`;
}

function bonusRule(p) {
  if (p.per_bird) return `${p.per_bird} pts per bird`;
  return `${p.lower_bound}–${p.upper_bound - 1}: <b>${p.lower_score}</b> · ${p.upper_bound}+: <b>${p.upper_score}</b>`;
}

// Progress toward a bonus card: every card scores from one count of qualifying birds.
function bonusProgress(b, { count: n, score }) {
  const unit = b.id === 23 ? "in hand" : b.id === 7 ? "in smallest habitat" : n === 1 ? "bird" : "birds";
  const p = b.params;
  if (p.per_bird) return `<div class="bn-prog"><span>${n} ${unit} × ${p.per_bird} = <b>${score} pts</b></span></div>`;
  const next = n >= p.upper_bound ? "top tier reached"
    : n >= p.lower_bound ? `${p.upper_bound - n} more for ${p.upper_score} pts`
    : `${p.lower_bound - n} more for ${p.lower_score} pts`;
  return `<div class="bn-prog">
    <div class="bn-bar"><i style="width:${Math.min(1, n / p.upper_bound) * 100}%"></i><s style="left:${(p.lower_bound / p.upper_bound) * 100}%"></s></div>
    <span><b>${n}</b> ${unit} · ${next}</span></div>`;
}

function bonusHtml(id, o = {}) {
  const b = C.bonuses[id];
  const pr = o.progress;
  return `<div class="bonus ${o.cls || ""}" ${o.attrs || ""}>
    <div class="bn-name">${b.name}</div><div class="bn-cond">${tok(b.condition)}</div>
    <div class="bn-rule">${bonusRule(b.params)}</div>
    ${pr ? `<div class="bn-now">now ${pr.score} pts</div>${bonusProgress(b, pr)}` : ""}</div>`;
}

function goalText(name) {
  let m;
  if ((m = name.match(/^eggs_in_(\w+)$/))) return `[egg] in [${m[1]}]`;
  if ((m = name.match(/^(\w+)_birds_with_egg$/))) return `[${m[1]}] birds with [egg]`;
  if ((m = name.match(/^birds_in_(\w+)$/))) return `Birds in [${m[1]}]`;
  if (name === "total_birds") return "Total birds";
  if (name === "sets_of_eggs") return "[egg] sets [forest][grassland][wetland]";
  return name;
}

const foodRow = (food, key = false) =>
  FOODS.map((f) => `<div class="food ${key ? hot(`food:${f}`) : ""}" ${key ? `data-click="key:food:${f}"` : ""}>${icon(f)}<b>${food[f] || 0}</b></div>`).join("");

// =============================================================================
// Render
// =============================================================================

function render() {
  renderHeader();
  renderBoard();
  renderSide();
  renderPrompt();
  renderHand();
  renderModal();
  renderLog();
}

function goalsHtml() {
  return S.goals
    .map((g, r) => {
      const vals = S.players.map((p, i) => {
        const v = g.status === "final" ? `${g.points[i]}` : g.status === "live" ? `${g.counts[i]}<small>·${g.points[i]}pt</small>` : "";
        return `<i style="--pc:${PCOLORS[i]}">${v}</i>`;
      });
      return `<div class="goal ${g.status === "live" ? "now" : ""} ${g.status === "final" ? "done" : ""}" data-goal="${r}">
        <div class="g-r">R${r + 1}</div><div class="g-t">${tok(goalText(g.name))}</div><div class="g-s">${vals.join("")}</div></div>`;
    })
    .join("");
}

// Hover panel for a goal: the goal board's placements, each player's points and what it takes to move up.
// Points the current round's goal would give this player if scored now.
const liveGoal = (i) => S.goals.find((g) => g.status === "live")?.points[i] || 0;

function goalPanel(r) {
  const g = S.goals[r], blue = S.scoring_mode === "blue";
  const ps = S.players.map((p, i) => ({ i, name: p.name, n: g.counts[i], pts: g.points[i] }));
  const chip = (p) => `<span class="who" style="--pc:${PCOLORS[p.i]}">${p.name}</span>`;
  const status = { final: "Scored", live: "In progress · if scored now", preview: "Preview · if scored now" }[g.status];

  let cols, place = () => "";
  if (blue) {
    cols = [0, 1, 2, 3, 4, 5].map((k) => ({ label: k === 5 ? "5+ items" : k === 1 ? "1 item" : `${k} items`, pts: k, who: ps.filter((p) => Math.min(p.n, 5) === k) }));
  } else {
    const table = [...GREEN_TABLE[r], 0, 0];
    const rank = (p) => ps.filter((q) => q.n > p.n).length;
    cols = ["1st", "2nd", "3rd", "4th+"].map((label, k) => ({
      label, pts: table[k],
      who: ps.filter((p) => (p.n === 0 ? 3 : Math.min(rank(p), 3)) === k),
    }));
    place = (p) => {
      if (!p.n) return "none → 0";
      const k = rank(p), tied = ps.filter((q) => q.n === p.n).length;
      if (tied === 1) return ORD[k];
      const spots = table.slice(k, k + tied);
      return `tied ${ORD[k]}: (${spots.join("+")}) ÷ ${tied}`;
    };
  }
  const hint = (p) => {
    if (g.status === "final") return "";
    if (blue) return p.n >= 5 ? "maxed" : `+${5 - p.n} to max`;
    const ahead = ps.filter((q) => q.n > p.n);
    if (ahead.length) {
      const next = ahead.reduce((a, b) => (b.n < a.n ? b : a));
      return `+${next.n - p.n + 1} to pass ${next.name}`;
    }
    const others = ps.filter((q) => q !== p);
    if (others.some((q) => q.n === p.n)) return "+1 to lead alone";
    return `leads by ${p.n - Math.max(...others.map((q) => q.n))}`;
  };

  return `<div class="gp-head"><b>Round ${r + 1}</b> · ${tok(goalText(g.name))}<span class="gp-status ${g.status}">${status}</span></div>
    <div class="gp-board ${blue ? "blue" : ""}" style="--cols:${cols.length}">
      ${cols.map((c) => `<div class="gp-col"><span>${c.label}</span><b>${c.pts}</b><div>${c.who.map(chip).join("")}</div></div>`).join("")}
    </div>
    <table class="gp-rows">${ps.map((p) => `<tr><td><span class="who" style="--pc:${PCOLORS[p.i]}">${p.name}</span></td>
      <td>${p.n}</td><td>${place(p)}</td><td><b>${p.pts} pts</b></td><td class="gp-hint">${hint(p)}</td></tr>`).join("")}</table>
    ${blue ? '<div class="gp-note">1 point per item, max 5.</div>' : '<div class="gp-note">Ties share the tied places\' points, rounded down. Having none of the item scores 0.</div>'}`;
}

function diceHtml() {
  return [0, 1, 2, 3, 4].map((k) => {
    const faces = S.feeder[k];
    if (!faces) return '<div class="die out"></div>';
    return `<div class="die ${faces.length > 1 ? "dual" : ""}">${faces
      .map((f) => `<span class="face ${hot(`die:${k}:${f}`)}" data-click="key:die:${k}:${f}">${icon(f)}</span>`)
      .join("")}</div>`;
  }).join("");
}

function renderHeader() {
  $("#round").textContent = S.game_over ? "Final" : `Round ${S.round} of 4`;
  $("#goals").innerHTML = goalsHtml();
  $("#players").innerHTML = S.players
    .map((p, i) => {
      const hand = Array.isArray(p.hand) ? p.hand.length : p.hand;
      return `<button class="ptab ${i === ui.view ? "viewing" : ""} ${i === S.turn_player && !S.game_over ? "turn" : ""}" data-click="view:${i}" style="--pc:${PCOLORS[i]}">
        <span class="p-top"><span class="p-name">${p.name}</span>${p.first ? '<span class="p-first" title="first player">1st</span>' : ""}<span class="p-score">${p.score.total}</span></span>
        <span class="p-meta"><span class="p-left" title="actions left this round"><i class="cube"></i><b>${p.cubes}</b>/${p.cubes_total}</span><span>${icon("card")}${hand}</span><span>${icon("egg")}${p.score.eggs}</span></span>
      </button>`;
    })
    .join("");
}

function renderBoard() {
  const p = S.players[ui.view];
  const mine = ui.view === S.human;
  const f = S.focus;
  const eggMode = mine && has("EggMapAction");
  let h = `<div class="b-name" style="--pc:${PCOLORS[ui.view]}">${mine ? "Your board" : `${p.name}'s board`}</div>`;
  // Cube track on the board's left edge: one slot per action row, holding this round's cubes
  const gutter = (r) => `<div class="gutter ${r < 0 ? "play" : ""}" style="--pc:${PCOLORS[ui.view]}">${'<i class="cube"></i>'.repeat(p.cubes_used.filter((x) => x === r).length)}</div>`;
  h += gutter(-1);
  h += `<div class="tile b-play ${mine ? hot("s:play_bird") : ""}" data-click="key:s:play_bird"><b>Play a bird</b><span>food + egg cost</span></div>`;
  h += EGG_COST.map((cost) => `<div class="b-cost">${cost ? tok("[egg]".repeat(cost)) : "<span>free</span>"}</div>`).join("");
  HAB.forEach((hab, r) => {
    const row = p.board[r], R = ROW[hab];
    const next = row.findIndex((x) => !x);
    const col = next < 0 ? 4 : next;
    const key = `hab:${hab}` in targets ? `hab:${hab}` : `s:${R.action}`;
    h += gutter(r);
    h += `<div class="tile row-tile ${hab} ${mine ? hot(key) : ""}" data-click="key:${key}">
      <div class="rt-hab">${icon(hab)}<span>${hab}</span></div>
      <div class="rt-act">${R.label}</div>
      <div class="rt-amt">${AMOUNTS[r][col]}<span>×</span>${icon(R.res)}</div>
      ${next < 0 || EXTRA[col] ? `<div class="rt-trade">${tok(R.trade)}</div>` : '<div class="rt-trade dim">no trade</div>'}
    </div>`;
    row.forEach((sp, c) => {
      if (sp) {
        const focus = f && f.player === ui.view && f.row === r && f.col === c ? "focus" : "";
        const cls = mine ? (eggMode ? (eggCan(sp.id) ? "hot" : "") : hot(`bird:${sp.id}`)) : "";
        h += `<div class="cell ${hab}">${cardHtml(sp.id, { state: sp, cls: `${cls} ${focus}`, pending: ui.eggs[sp.id], attrs: `data-click="board:${sp.id}" data-board="${ui.view}"` })}</div>`;
      } else {
        const can = mine && ui.sel !== null && playSpot(r, c) ? "hot" : "";
        h += `<div class="cell ${hab}"><div class="spot ${can}" data-click="spot:${r},${c}">
          <div class="sp-amt">${AMOUNTS[r][c]}×${icon(R.res)}</div>
          ${EXTRA[c] ? `<div class="sp-trade">${tok(R.trade)}</div>` : ""}</div></div>`;
      }
    });
  });
  $("#board").innerHTML = h;
}

function renderSide() {
  const drawMode = has("DrawCardsAction");
  $("#feeder").innerHTML = `<div class="dice">${diceHtml()}</div>` +
    ("s:reroll_all" in targets ? `<button class="ghost small" data-click="key:s:reroll_all">Reroll feeder</button>` : "");

  const tray = S.tray.map((id) => {
    const on = ui.draw.tray.includes(id);
    const can = drawMode ? (on || drawFits({ ...ui.draw, tray: [...ui.draw.tray, id] }).length ? "hot" : "") : hot(`bird:${id}`);
    return cardHtml(id, { cls: `${can} ${on ? "sel" : ""}`, attrs: `data-click="tray:${id}"` });
  });
  const deckCan = drawMode && drawFits({ ...ui.draw, deck: ui.draw.deck + 1 }).length ? "hot" : "";
  tray.push(`<div class="deck ${deckCan}" data-click="deck"><span>${S.deck}</span>${ui.draw.deck ? `<b>+${ui.draw.deck}</b>` : ""}</div>`);
  $("#tray").innerHTML = tray.join("");

  const p = S.players[ui.view];
  const mine = ui.view === S.human;
  const bonus = Array.isArray(p.bonus)
    ? p.bonus.map((b) => bonusHtml(b, { progress: p.bonus_progress[b] })).join("")
    : `<div class="hidden-bonus">${p.bonus} hidden bonus card${p.bonus === 1 ? "" : "s"} · ${Array.isArray(p.hand) ? p.hand.length : p.hand} cards in hand</div>`;
  const sc = p.score;
  $("#supply").innerHTML = `<h3>${mine ? "Your supply" : `${p.name}'s supply`}</h3>
    <div class="foods">${foodRow(p.food, mine)}</div>
    <h3>Bonus cards</h3><div class="bonuses">${bonus}</div>
    <h3>Score</h3><div class="score">
      ${[["Birds", sc.birds], ["Bonus", sc.bonus], ["Goals", sc.goals, liveGoal(ui.view)], ["Eggs", sc.eggs], ["Cached", sc.cached], ["Tucked", sc.tucked]]
        .map(([k, v, live]) => `<span>${k}<b>${v}${live ? `<small title="this round's goal, if scored now"> +${live}</small>` : ""}</b></span>`).join("")}
      <span class="total">Total<b>${sc.total}</b></span></div>`;
}

function renderPrompt() {
  const el = $("#prompt");
  if (S.game_over) {
    el.innerHTML = `<div class="p-text">Game over</div><div class="p-choices"><button class="primary" data-click="scores">Final scores</button><button class="ghost" data-click="new">New game</button></div>`;
    return;
  }
  if (!S.actions.length) {
    const p = S.players[S.current];
    const last = [...S.log].reverse().find((e) => e.text);
    el.innerHTML = `<div class="p-text thinking"><span class="who" style="--pc:${PCOLORS[S.current]}">${p.name}</span> is thinking<span class="dots"></span></div>
      ${last ? `<div class="p-last"><span class="who" style="--pc:${PCOLORS[last.p]}">${S.players[last.p].name}</span> ${tok(last.text)}</div>` : ""}`;
    return;
  }
  const builder = ["PlayBirdAction", "EggMapAction", "DrawCardsAction", "SelectInitialAction"];
  const seen = new Set();
  const buttons = S.actions
    .filter((a) => !builder.includes(a.t) && !seen.has(a.label) && seen.add(a.label))
    .map((a) => `<button class="choice" data-click="act:${a.i}" ${a.t === "IdAction" && BIRD_ID.has(a.type) ? `data-bird="${a.id}"` : ""}>${tok(a.label)}</button>`);

  let extra = "";
  if (has("EggMapAction")) {
    const need = Math.max(...eggActs().map(({ m }) => sum(Object.values(m))));
    extra = `<span class="hint">Click birds to place eggs · ${sum(Object.values(ui.eggs))} / ${need}</span><button class="ghost small" data-click="reset">Reset</button>`;
  } else if (has("DrawCardsAction")) {
    extra = `<span class="hint">Click tray cards or the deck</span><button class="ghost small" data-click="reset">Reset</button>`;
  } else if (has("PlayBirdAction")) {
    extra = ui.sel === null
      ? `<span class="hint">Highlighted birds in your hand are playable</span>`
      : `<span class="hint">Place <b>${bird(ui.sel).name}</b> on a highlighted spot</span><button class="ghost small" data-click="cancel">Cancel</button>`;
  }
  el.innerHTML = `<div class="p-text"><span class="who" style="--pc:${PCOLORS[S.human]}">You</span> ${tok(S.prompt)}</div>
    <div class="p-choices">${buttons.join("")}${extra}</div>`;
}

function renderHand() {
  const hand = human().hand;
  const playable = new Set(playActs().map((a) => a.bird_id));
  $("#hand").innerHTML =
    hand
      .map((id) => {
        const cls = [playable.has(id) || hot(`bird:${id}`) ? "hot" : "", ui.sel === id ? "sel" : ""].join(" ");
        return cardHtml(id, { cls, attrs: `data-click="hand:${id}"` });
      })
      .join("") || '<div class="empty">No birds in hand</div>';
  // Keep the hand up while a hand card must be picked; drop it once a bird is chosen so the board is clear.
  const needHand = hand.some((id) => playable.has(id) || `bird:${id}` in targets);
  $("#dock").classList.toggle("raised", needHand && ui.sel === null);
}

function renderModal() {
  const m = $("#modal");
  const offer = S.actions.filter((a) => a.type === "power_5_bonus");
  if (offer.length) {
    m.hidden = false;
    m.innerHTML = `<div class="sheet"><h2>Choose a bonus card to keep</h2><p>${tok(S.prompt)}</p>
      <div class="m-bonus">${offer.map((a) => bonusHtml(a.id, { progress: S.bonus_offer[a.id], cls: "hot", attrs: `data-click="act:${a.i}"` })).join("")}</div>
      <div class="m-foot"><div></div><span class="m-label">The other card${offer.length > 2 ? "s are" : " is"} discarded.</span></div></div>`;
    return;
  }
  if (S.phase === "select_initial_cards" && S.actions.length) {
    const bonuses = [...new Set(S.actions.map((a) => a.kept_bonus))];
    const n = ui.init.birds.length;
    const food = human().food, disc = ui.init.food;
    const k = sum(Object.values(disc));
    const ok = initAction() && k === n;
    const label = !n ? "Keep no birds"
      : k === n ? `Keep ${n} bird${n === 1 ? "" : "s"}, discard ${n} food`
      : k < n ? `Pick ${n - k} more food to discard`
      : `Discard only ${n} food`;
    const chips = FOODS.map((f) => `<div class="food pick ${disc[f] ? "out" : ""}" data-click="init-food:${f}">${icon(f)}<b>${(food[f] || 0) - (disc[f] || 0)}</b></div>`).join("");
    m.hidden = false;
    m.innerHTML = `<div class="sheet"><h2>Choose your starting hand</h2>
      <p>Keep any birds — each one costs 1 food (you start with one of each). Then keep 1 bonus card.</p>
      <div class="m-table">
        <div><div class="m-label">Round goals</div><div class="m-goals">${goalsHtml()}</div></div>
        <div><div class="m-label">Bird tray</div><div class="m-tray">${S.tray.map((id) => cardHtml(id)).join("")}</div></div>
        <div><div class="m-label">Birdfeeder</div><div class="dice">${diceHtml()}</div></div>
      </div>
      <div class="m-cards">${human().hand.map((id) => cardHtml(id, { cls: ui.init.birds.includes(id) ? "kept" : "tossed", attrs: `data-click="init-bird:${id}"` })).join("")}</div>
      <div class="m-bonus">${bonuses.map((b) => bonusHtml(b, { cls: ui.init.bonus === b ? "kept" : "tossed", attrs: `data-click="init-bonus:${b}"` })).join("")}</div>
      <div class="m-foot"><div><div class="m-label">Click food to discard (1 per bird kept)</div><div class="foods">${chips}</div></div>
      <button class="primary" data-click="init-ok" ${ok ? "" : "disabled"}>${label}</button></div></div>`;
    return;
  }
  if (S.game_over && ui.showScores) {
    const rows = [["Birds", "birds"], ["Bonus cards", "bonus"], ["Round goals", "goals"], ["Eggs", "eggs"], ["Cached food", "cached"], ["Tucked cards", "tucked"], ["Total", "total"]];
    const best = Math.max(...S.players.map((p) => p.score.total));
    m.hidden = false;
    m.innerHTML = `<div class="sheet scores"><h2>Final scores</h2><table>
      <tr><th></th>${S.players.map((p, i) => `<th style="--pc:${PCOLORS[i]}" class="${p.score.total === best ? "win" : ""}">${p.name}</th>`).join("")}</tr>
      ${rows.map(([l, k]) => `<tr class="r-${k}"><td>${l}</td>${S.players.map((p) => `<td>${p.score[k]}</td>`).join("")}</tr>`).join("")}
      </table><div class="m-foot"><button class="ghost" data-click="close">View boards</button><button class="primary" data-click="new">New game</button></div></div>`;
    return;
  }
  m.hidden = true;
  m.innerHTML = "";
}

function renderLog() {
  const el = $("#log");
  el.innerHTML = "<h3>Game log</h3>" + S.log
    .map((e) => (e.round ? `<h4>Round ${e.round}</h4>` : `<div><span class="who" style="--pc:${PCOLORS[e.p]}">${S.players[e.p].name}</span> ${tok(e.text)}</div>`))
    .join("");
  el.scrollTop = el.scrollHeight;
}

// =============================================================================
// Input
// =============================================================================

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-click]");
  if (!el || busy) return;
  const raw = el.dataset.click;
  const sep = raw.indexOf(":");
  const kind = sep < 0 ? raw : raw.slice(0, sep);
  const arg = sep < 0 ? "" : raw.slice(sep + 1);
  const id = Number(arg);
  const mine = ui.view === S.human;
  switch (kind) {
    case "act": return act(id);
    case "key": if (arg in targets && (mine || arg.startsWith("die") || arg.startsWith("s:reroll"))) act(targets[arg]); return;
    case "view": ui.view = id; return render();
    case "hand":
      if (has("PlayBirdAction") && playActs().some((a) => a.bird_id === id)) { ui.sel = ui.sel === id ? null : id; return render(); }
      if (`bird:${id}` in targets) act(targets[`bird:${id}`]);
      return;
    case "tray":
      if (has("DrawCardsAction")) return drawToggle(id);
      if (`bird:${id}` in targets) act(targets[`bird:${id}`]);
      return;
    case "deck": if (has("DrawCardsAction")) drawTry({ ...ui.draw, deck: ui.draw.deck + 1 }); return;
    case "board":
      if (!mine) return;
      if (has("EggMapAction")) return eggAdd(id);
      if (`bird:${id}` in targets) act(targets[`bird:${id}`]);
      return;
    case "spot": {
      const [r, c] = arg.split(",").map(Number);
      const a = mine && ui.sel !== null && playSpot(r, c);
      if (a) act(a.i);
      return;
    }
    case "reset": ui.eggs = {}; ui.draw = { tray: [], deck: 0 }; return render();
    case "cancel": ui.sel = null; return render();
    case "init-bird": {
      const b = ui.init.birds;
      ui.init.birds = b.includes(id) ? b.filter((x) => x !== id) : [...b, id];
      return render();
    }
    case "init-bonus": ui.init.bonus = id; return render();
    case "init-food": {
      const d = ui.init.food, have = human().food[arg] || 0;
      ui.init.food = { ...d, [arg]: (d[arg] || 0) < have ? (d[arg] || 0) + 1 : 0 };
      return render();
    }
    case "init-ok": {
      const a = initAction();
      if (!a || sum(Object.values(ui.init.food)) !== ui.init.birds.length) return;
      ui.discard = ui.init.birds.length ? { ...ui.init.food } : null;
      return act(a.i);
    }
    case "scores": ui.showScores = true; return render();
    case "close": ui.showScores = false; return render();
    case "new": ui.showScores = true; return newGame().then(set);
  }
});

$("#log-btn").addEventListener("click", () => ($("#log").hidden = !$("#log").hidden));

// Goal standings panel under any hovered goal tile.
const goalPop = $("#goalpop");
document.addEventListener("mouseover", (e) => {
  const el = e.target.closest("[data-goal]");
  if (!el) return (goalPop.hidden = true);
  goalPop.innerHTML = goalPanel(Number(el.dataset.goal));
  goalPop.hidden = false;
  const box = el.getBoundingClientRect();
  goalPop.style.top = `${box.bottom + 8}px`;
  goalPop.style.left = `${Math.min(box.left, innerWidth - goalPop.offsetWidth - 12)}px`;
});

// Large preview of any hovered card, pinned to the right side.
const preview = $("#preview");
document.addEventListener("mouseover", (e) => {
  const el = e.target.closest("[data-bird]");
  if (!el || el.closest("#preview") || el.closest(".m-cards")) return preview.classList.remove("show");
  const id = Number(el.dataset.bird);
  let state;
  if (el.dataset.board !== undefined) {
    state = S.players[Number(el.dataset.board)].board.flat().find((b) => b && b.id === id);
  }
  preview.innerHTML = cardHtml(id, { state });
  preview.classList.add("show");
});

(async () => {
  C = await api("/api/cards");
  const resume = new URLSearchParams(location.search).has("g");
  set(await (resume ? api(gameUrl("")).catch(newGame) : newGame()));
})();
