// The lab UI. One request (/api/overview) holds everything; each page is a function from that to HTML.
// Charts are small SVG builders below: no library.

let S = null; // the overview
let xMode = "generation"; // Progress page: x axis by generation or by cumulative compute
let logName = null; // Queue page: the log shown
let lastText = "";

// ---------- formatting ----------
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const num = (x, d = 0) => (x == null ? "–" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (x, d = 0) => (x == null ? "–" : (100 * x).toFixed(d) + "%");
const pts = (x) => (x == null ? "–" : (x < 0 ? "−" : "+") + Math.abs(x).toFixed(1));
const pm = (x, ci) => (x == null ? "–" : `${pts(x)} ± ${ci == null ? "?" : ci.toFixed(1)}`);
const when = (iso) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–");
const last = (a) => a[a.length - 1];
const newest = (a) => a.slice().reverse(); // the ledger and the server's lists are oldest first. On screen: vertical lists newest on top,
// anything laid out left to right (lineage, tabs, chart axes) in historical order
const sum = (a) => a.reduce((x, y) => x + y, 0);
const chip = (status, text) => `<span class="chip ${esc(status)}">${esc(text ?? status)}</span>`;
const tile = (label, value, sub = "", meter = null) =>
  `<div class="card tile"><div class="label">${label}</div><div class="value">${value}</div>` +
  (meter == null ? "" : `<div class="meter"><i style="width:${Math.min(100, 100 * meter)}%"></i></div>`) +
  `<div class="sub">${sub}</div></div>`;
const table = (head, rows) =>
  `<div class="scroll"><table><tr>${head.map((h) => `<th${h.startsWith(">") ? ' class="r"' : ""}>${h.replace(/^>/, "")}</th>`).join("")}</tr>${rows.join("")}</table></div>`;
const tr = (cells, attrs = "") => `<tr ${attrs}>${cells.map((c) => (String(c).startsWith(">") ? `<td class="r">${String(c).slice(1)}</td>` : `<td>${c}</td>`)).join("")}</tr>`;
const legend = (items) => `<div class="legend">${items.map(([name, color]) => `<span><i style="background:${color}"></i>${esc(name)}</span>`).join("")}</div>`;

// ---------- what the ledger says ----------
const events = (kind, g) => S.events.filter((e) => e.kind === kind && (g == null || e.generation === g));
const generationData = (g) => S.generations.find((x) => x.generation === g);
const promoted = (g) => last(events("verdict", g).filter((v) => v.result === "promoted"));
// The nets a generation is judged by: the policy that was promoted (else the last trained), the value net in use
const policyOf = (g) => (promoted(g) && events("train_policy", g).find((e) => e.net === promoted(g).net)) || last(events("train_policy", g));
const valueOf = (g) => last(events("train_value", g).filter((e) => /value\.pt$/.test(e.out))) || last(events("train_value", g));
const matchOf = (role, g) => last(S.matches.filter((m) => m.role === role && m.generation === g));
const vrow = (t, name) => t?.validation.find((r) => r.name === name);
const matchId = (m) => m.runs[0];
const folderGeneration = (folder) => { const m = /^selfplay(?:_g(\d+))?(?:_homelab)?$/.exec(folder); return m ? +(m[1] ?? 0) : null; };
const trainings = () => S.events.filter((e) => e.kind.startsWith("train_"));
// Names. Nothing is shown as it is stored: a net is named by its kind, the generation it was trained in and
// the order of training ("Policy G1", "Policy G1 #2"; its file hash stays in the tooltip); folders, files,
// phases, labels and commands are spelled out.
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const human = (s) => String(s ?? "").replace(/_/g, " ");
function netNames() {
  if (S._nets) return S._nets;
  const names = {}, count = {};
  for (const e of trainings()) {
    const key = e.kind + e.generation;
    count[key] = (count[key] ?? 0) + 1;
    names[e.net] ??= `${e.kind === "train_policy" ? "Policy" : "Value net"} G${e.generation}` + (count[key] > 1 ? ` #${count[key]}` : "");
  }
  return (S._nets = names);
}
const netText = (id) => netNames()[id] ?? "a net from before the ledger";
// Policy and value nets are different things: each has its mark (a violet diamond, a pink disc) before its name
// everywhere, and lists of nets are split by kind, never interleaved.
const KINDS = [["policy", "Policy nets", "train_policy"], ["value", "Value nets", "train_value"]];
const kindOf = (id) => ({ train_policy: "policy", train_value: "value" })[trainings().find((e) => e.net === id)?.kind] ?? "";
const mark = (kind) => (kind ? `<i class="kind ${kind}"></i>` : "");
const net = (id) => `<a class="net" href="#net/${encodeURIComponent(id)}" title="file hash ${esc(id)}">${mark(kindOf(id))}${esc(netText(id))}</a>`;
const netName = (e) => netText(e.net);
const folderName = (f) => { const g = folderGeneration(f); return g == null ? human(f) : `generation ${g}, ${/_homelab$/.test(f) ? "home server" : "laptop"}`; };
const TITLES = { sanity: "Policy alone: candidate vs champion", decision: "PUCT: candidate vs champion", anchor_policy: "Policy alone vs the plain tree", anchor_puct: "PUCT vs the plain tree", leaf: "Value net at the leaves" };
const matchTitle = (m) => TITLES[m.role] ?? cap(human(m.experiment));
const FILES = { "policy.bin": "champion policy", "policy_candidate.bin": "candidate policy", "value.bin": "value net in use", "value_candidate.bin": "candidate value net" };
const fileName = (f) => FILES[f.split("/").pop()] ?? human(f.split("/").pop().replace(/\.\w+$/, ""));
const logTitle = (f) => cap(human(f.replace(/\.log$/, "").replace(/^(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)\d\d-\d+_(.*)$/, "$6, $3/$2 $4:$5")));
function commandName(c) {
  const out = /\s-o\s+(\S+)/.exec(c)?.[1].replace(/\/$/, "").split("/").pop(), match = S.matches.find((m) => m.experiment === out);
  if (/-m lab\.dataset/.test(c)) return "Building a training window";
  if (/-m lab\.train_policy/.test(c)) return "Training a policy";
  if (/-m lab\.train_value/.test(c)) return "Training a value net";
  if (/-m lab\.prior_vs_search/.test(c)) return "Search vs prior check";
  if (/-m lab\.tune/.test(c)) return "Tuning the search";
  if (out) return folderGeneration(out) != null ? `Self-play, ${folderName(out)}` : `Match: ${match ? matchTitle(match) : cap(human(out))}`;
  return /-m lab/.test(c) ? "A lab run" : c;
}
const genColor = (g) => `var(--s${(g % 4) + 1})`; // generations of games: four hues, apart from the two of the kinds of net
// A net's training window: the games it saw, by the generation that played them
function windowBar(e) {
  const total = sum(Object.values(e.window)), byGen = {};
  for (const [f, n] of Object.entries(e.window)) byGen[folderGeneration(f)] = (byGen[folderGeneration(f)] ?? 0) + n;
  const gens = Object.keys(byGen).sort((a, b) => b - a);
  return `<div class="meter split" style="max-width:420px">${gens.map((g) => `<i style="width:${(100 * byGen[g]) / total}%;background:${genColor(+g)}" data-tip="${Object.entries(e.window).filter(([f]) => folderGeneration(f) == g).map(([f, n]) => `${folderName(f)}: ${num(n)} games`).join("\n")}"></i>`).join("")}</div>` +
    legend(gens.map((g) => [`generation ${g} games: ${num(byGen[g])}`, genColor(+g)]));
}
const PARTS = { score: "total_score", birds: "bird_points", eggs: "egg_points", cached: "cached_food", tucked: "tucked_cards", goals: "round_goals", bonus: "bonus_scores", "food left": "food_tokens" };
const SCORE_PARTS = ["birds", "eggs", "cached", "tucked", "goals", "bonus"];
const ROLE = { sanity: "sanity check", decision: "decision", anchor_policy: "anchor", anchor_puct: "anchor", leaf: "value net at the leaves", experiment: "experiment" };

// The checks of docs/SELFPLAY_LOOP.md that can be computed: {label, status ok|warn|todo, detail}
function checks(g) {
  const G = generationData(g), out = [];
  const add = (step, label, status, detail) => out.push({ step, label, status, detail });
  if (G) {
    add(2, "No deal played twice", G.deals === G.games ? "ok" : "warn", `${num(G.games)} games on ${num(G.deals)} deals`);
    const s = G.seats;
    if (s) add(2, "Seats are even", Math.abs(s.win_rate - 0.5) <= s.win_ci && Math.abs(s.score_diff) <= s.diff_ci ? "ok" : "warn",
      `${esc(human(s.arm))} wins ${pct(s.win_rate, 1)} ± ${pct(s.win_ci, 1)}, ${pm(s.score_diff, s.diff_ci)} points`);
  }
  const pvs = last(events("prior_vs_search", g)), all = pvs?.phases.find((p) => p.phase === "all");
  if (g) add(2, "The search still overrules its prior", !all ? "todo" : all.search_keeps_policy_top < 0.9 ? "ok" : "warn",
    all ? `it keeps the policy's top move ${pct(all.search_keeps_policy_top)} of the time (alarm near 90%)` : "prior vs search not run yet");
  const p = policyOf(g), v = valueOf(g);
  if (p?.epochs.length) {
    const e = last(p.epochs), gap = e.val_ce - e.train_ce;
    add(5, "Policy isn't memorizing", gap <= 0.015 ? "ok" : "warn", `validation − training cross-entropy ${gap.toFixed(3)} (above ~0.01 is memorizing)`);
  }
  if (p) {
    const rows = ["main_turn", "play_bird", "draw_cards"].map((n) => vrow(p, n)).filter(Boolean);
    add(5, "Policy beats the kind prior where it matters", rows.every((r) => r.top.net - r.top.kind >= 0.1) ? "ok" : "warn",
      rows.map((r) => `${human(r.name)} ${pct(r.top.net)} vs ${pct(r.top.kind)}`).join(", "));
  }
  if (v) {
    const a = vrow(v, "all"), rounds = ["r1", "r2", "r3", "r4"];
    add(5, "Value net beats the score-gap line in every round", rounds.every((r) => a.net[r].acc > a.line[r].acc) ? "ok" : "warn",
      rounds.map((r) => `${r} ${pct(a.net[r].acc)} vs ${pct(a.line[r].acc)}`).join(", "));
    if (v.epochs.length) {
      const best = Math.min(...v.epochs.map((e) => e.val_mse)), end = last(v.epochs).val_mse;
      add(5, "Value net's validation error doesn't climb", end - best <= 0.01 ? "ok" : "warn", `best ${best.toFixed(3)}, last epoch ${end.toFixed(3)}`);
    }
  }
  return out;
}

// The iteration of generation g as the 8 steps of docs/SELFPLAY_LOOP.md
function steps(g) {
  const G = generationData(g), c = checks(g), verdict = last(events("verdict", g)), decision = matchOf("decision", g);
  const worst = (step) => { const s = c.filter((x) => x.step === step).map((x) => x.status); return s.includes("warn") ? "warn" : s.includes("todo") || !s.length ? "todo" : "ok"; };
  const trained = policyOf(g) && valueOf(g);
  const arm = decision?.arms[0];
  const list = [
    ["Collect", G.games >= S.target_games ? "ok" : "todo", `${num(G.games)} / ${num(S.target_games)} games`],
    ["Check the data", worst(2), c.filter((x) => x.step === 2 && x.status !== "ok").map((x) => x.label).join("; ") || "all checks pass"],
    ["Build the window", events("dataset", g).length || trained ? "ok" : "todo", trained ? `${num(sum(Object.values(policyOf(g).window)))} games` : ""],
    ["Train", trained ? "ok" : "todo", trained ? `${netName(policyOf(g))}, ${netName(valueOf(g))}` : ""],
    ["Check the training", trained ? worst(5) : "todo", c.filter((x) => x.step === 5 && x.status !== "ok").map((x) => x.label).join("; ") || (trained ? "all checks pass" : "")],
    ["Matches", verdict ? "ok" : "todo", arm ? `candidate ${pm(arm.per_seed_diff, arm.per_seed_ci)}${verdict ? ": " + verdict.result : ""}` : verdict ? verdict.result : ""],
    ["Start the next generation", generationData(g + 1) ? "ok" : "todo", verdict?.result === "rejected" ? "rejected: this generation grows" : ""],
    ["Record", "manual", "EXPERIMENTS.md, backup"],
  ];
  const current = list.findIndex(([, status]) => status === "todo" || status === "warn");
  return list.map(([title, status, detail], i) => ({ title, status, detail, current: i === current }));
}

// ---------- charts ----------
function ticks(lo, hi, n = 4) {
  const span = hi - lo || 1, mag = 10 ** Math.floor(Math.log10(span / n));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n + 1);
  const out = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

// series: [{name, color, pts: [{x, y, lo, hi, tip}], band, dots}]; xTicks: [{x, label}]; refs: [{y, label}] horizontal lines;
// marks: [{x, label, tip}] vertical ones (moments), their labels staggered
// The width inside a card when n sections share the page (.cols stacks them on a narrow window)
const cardW = (n = 1) => { if (innerWidth <= 1300) n = 1; return Math.max(320, Math.floor((document.getElementById("main").clientWidth - 56 - 24 * (n - 1)) / n) - 34); };

function lineChart({ series, xTicks, refs = [], marks = [], yFmt = (v) => v, w = 520, h = 220, labels = true }) {
  const all = series.flatMap((s) => s.pts).filter((p) => p.y != null);
  if (!all.length) return `<p class="muted">Nothing measured yet.</p>`;
  const m = { l: 44, r: labels ? 96 : 14, t: 10, b: 24 };
  const xs = [...all.map((p) => p.x), ...xTicks.map((t) => t.x), ...marks.map((k) => k.x)];
  let [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  if (x0 === x1) [x0, x1] = [x0 - 1, x1 + 1];
  const ys = [...all.flatMap((p) => [p.y, p.lo ?? p.y, p.hi ?? p.y]), ...refs.map((r) => r.y)];
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const pad = (y1 - y0 || Math.abs(y1) || 1) * 0.1;
  [y0, y1] = [y0 - pad, y1 + pad];
  const X = (x) => m.l + ((x - x0) / (x1 - x0)) * (w - m.l - m.r), Y = (y) => m.t + (1 - (y - y0) / (y1 - y0)) * (h - m.t - m.b);
  let svg = "";
  for (const t of ticks(y0, y1)) svg += `<line class="grid-line" x1="${m.l}" x2="${w - m.r}" y1="${Y(t)}" y2="${Y(t)}"/><text x="${m.l - 6}" y="${Y(t) + 4}" text-anchor="end">${yFmt(t)}</text>`;
  for (const t of xTicks) svg += `<text x="${X(t.x)}" y="${h - 6}" text-anchor="middle">${esc(t.label)}</text>`;
  for (const r of refs) svg += `<line class="ref" x1="${m.l}" x2="${w - m.r}" y1="${Y(r.y)}" y2="${Y(r.y)}"/><text x="${w - m.r - 4}" y="${Y(r.y) - 4}" text-anchor="end">${esc(r.label)}</text>`;
  marks.forEach((k, i) => {
    svg += `<line class="ref" x1="${X(k.x)}" x2="${X(k.x)}" y1="${m.t}" y2="${h - m.b}"/><text x="${X(k.x) - 4}" y="${m.t + 10 + (i % 6) * 13}" text-anchor="end">${esc(k.label)}</text>` +
      `<rect x="${X(k.x) - 5}" y="${m.t}" width="10" height="${h - m.t - m.b}" fill="transparent" data-tip="${esc(k.tip ?? k.label)}"/>`;
  });
  const ends = [];
  for (const s of series) {
    const p = s.pts.filter((q) => q.y != null);
    if (!p.length) continue;
    if (s.band) svg += `<polygon fill="${s.color}" opacity="0.14" points="${p.map((q) => `${X(q.x)},${Y(q.hi)}`).join(" ")} ${p.slice().reverse().map((q) => `${X(q.x)},${Y(q.lo)}`).join(" ")}"/>`;
    svg += `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="${p.map((q) => `${X(q.x)},${Y(q.y)}`).join(" ")}"/>`;
    for (const q of p) {
      if (!s.band && q.lo != null) svg += `<line stroke="${s.color}" stroke-width="1.5" x1="${X(q.x)}" x2="${X(q.x)}" y1="${Y(q.lo)}" y2="${Y(q.hi)}"/>`;
      if (s.dots !== false) svg += `<circle cx="${X(q.x)}" cy="${Y(q.y)}" r="4" fill="${s.color}" stroke="var(--surface)" stroke-width="2"/>`;
      svg += `<circle cx="${X(q.x)}" cy="${Y(q.y)}" r="${s.dots === false ? 4 : 11}" fill="transparent" data-tip="${esc(q.tip ?? `${s.name}: ${yFmt(q.y)}`)}"/>`;
    }
    ends.push({ y: Y(last(p).y), name: s.name });
  }
  if (labels) {
    ends.sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 13); // keep the labels apart
    for (const e of ends) svg += `<text x="${w - m.r + 8}" y="${e.y + 4}">${esc(e.name)}</text>`;
  }
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}">${svg}</svg>`;
}

// One row of a forest plot: a value and its interval on a domain shared by the rows. Filled when the
// interval excludes zero.
function forest(v, ci, [lo, hi], w = 220) {
  if (v == null) return "";
  const X = (x) => 6 + ((x - lo) / (hi - lo)) * (w - 12), c = ci ?? 0, clear = Math.abs(v) > c;
  return `<svg viewBox="0 0 ${w} 20" width="${w}" data-tip="${pm(v, ci)} points per game"><line class="ref" x1="${X(0)}" x2="${X(0)}" y1="0" y2="20"/>` +
    `<line stroke="var(--s1)" stroke-width="2" stroke-linecap="round" x1="${X(v - c)}" x2="${X(v + c)}" y1="10" y2="10"/>` +
    `<circle cx="${X(v)}" cy="10" r="4.5" fill="${clear ? "var(--s1)" : "var(--surface)"}" stroke="var(--s1)" stroke-width="2"/></svg>`;
}
const domain = (rows) => { const e = Math.max(1, ...rows.map(([v, ci]) => Math.abs(v ?? 0) + (ci ?? 0))) * 1.08; return [-e, e]; };

// A bar from zero, on a shared domain: blue above, red below
function bar(v, [lo, hi], tip, w = 220) {
  const X = (x) => 6 + ((x - lo) / (hi - lo)) * (w - 12), a = Math.min(X(0), X(v)), len = Math.abs(X(v) - X(0));
  return `<svg viewBox="0 0 ${w} 18" width="${w}" data-tip="${esc(tip)}"><rect x="${a}" y="3" width="${Math.max(len, 1)}" height="12" rx="3" fill="var(${v < 0 ? "--neg" : "--s1"})"/>` +
    `<line class="ref" x1="${X(0)}" x2="${X(0)}" y1="0" y2="18"/></svg>`;
}

// Mean score per generation, stacked by where the points come from
function scoreBars(gens, w = 640) {
  const rowH = 34, l = 56, max = Math.max(...gens.map((G) => G.parts.score)) * 1.08;
  let svg = "";
  gens.forEach((G, i) => {
    let x = l;
    const y = i * rowH + 6;
    svg += `<text x="${l - 8}" y="${y + 15}" text-anchor="end">gen ${G.generation}</text>`;
    SCORE_PARTS.forEach((part, k) => {
      const len = (G.parts[part] / max) * (w - l - 50);
      svg += `<rect x="${x}" y="${y}" width="${Math.max(len - 2, 1)}" height="22" rx="3" fill="var(--s${k + 1})" data-tip="generation ${G.generation}: ${part} ${G.parts[part].toFixed(1)}"/>`;
      x += len;
    });
    svg += `<text x="${x + 4}" y="${y + 15}">${G.parts.score.toFixed(1)}</text>`;
  });
  return legend(SCORE_PARTS.map((p, k) => [p, `var(--s${k + 1})`])) + `<svg viewBox="0 0 ${w} ${gens.length * rowH + 6}" width="${w}">${svg}</svg>`;
}

// ---------- pages ----------
function describe(e) {
  if (e.kind === "verdict") return `${net(e.net)} ${chip(e.result)}`;
  if (e.kind === "train_policy") return `${net(e.net)} trained: the search's top move ${pct(vrow(e, "all")?.top.net)}`;
  if (e.kind === "train_value") return `${net(e.net)} trained: winner ${pct(vrow(e, "all")?.net.all.acc)} (score-gap line ${pct(vrow(e, "all")?.line.all.acc)})`;
  if (e.kind === "prior_vs_search") return `Search keeps the policy's top move ${pct(e.phases.find((p) => p.phase === "all")?.search_keeps_policy_top)} of the time`;
  if (e.kind === "dataset") return `Training window built: ${num(e.games)} games`;
  if (e.kind === "match") return `<a href="#match/${matchId(e)}">${esc(matchTitle(e))}</a>: ` + e.arms.map((a) => `${esc(human(a.arm))} ${pm(a.per_seed_diff, a.per_seed_ci)}`).join(", ");
  return esc(e.kind);
}

function stepper(g) {
  const sign = { ok: "✓ done", warn: "! look", todo: "to do", manual: "by hand" };
  return `<ol class="steps">${steps(g).map((s, i) =>
    `<li class="${s.current ? "current" : ""}"><div class="n">${i + 1} · ${sign[s.status]}</div><div class="t">${s.title}</div><div class="d">${esc(s.detail)}</div></li>`).join("")}</ol>`;
}

// Stop button for a command: by process on this machine, or the home server's container
const stopButton = ({ pid, home }, what) => `<button class="stop" ${home ? "data-stop-home" : `data-stop-pid="${pid}"`} data-what="${esc(what)}">Stop</button>`;
// The lab command writing to a folder (-o <folder>), if it runs on this machine
const commandFor = (folder) => S.compute[0].jobs.find((j) => new RegExp(`-o\\s+\\S*\\b${folder}/?(\\s|$)`).test(j.command));

// What is running, one row per activity. The queue job, the lab command it started and the process using the
// threads are the same thing: the row comes from the command, and says whether the queue started it.
function running() {
  const rows = [], home = S.compute.find((c) => c.name === "home server");
  const out = (j) => /\s-o\s+\S*?([^/\s]+)\/?(\s|$)/.exec(j.command)?.[1];
  for (const j of S.compute[0].jobs) {
    const folder = out(j), queued = S.jobs.find((x) => x.id === j.queue_job), match = S.matches.find((m) => m.running && m.experiment === folder);
    const source = S.generations.flatMap((G) => G.sources).find((x) => x.folder === folder);
    const detail = source ? `${num(source.games)} games, ${num(source.per_hour)} in the last hour`
      : match ? (match.progress ? `${num(match.games)}${match.total ? " of " + num(match.total) : ""} games` : `<span class="muted">${match.total ? num(match.total) + " games; " : ""}progress unknown until its file closes</span>`) : "";
    const meter = match?.progress && match.total ? `<div class="meter"><i style="width:${(100 * match.games) / match.total}%"></i></div>` : "";
    rows.push(tr([chip("running", "laptop"), `<span title="${esc(j.command)}">${match ? `<a href="#match/${matchId(match)}">${esc(commandName(j.command))}</a>` : esc(commandName(j.command))}</span>${meter}`,
      detail, `<span class="muted">${queued ? "queue, since " + when(queued.started) : "started outside the queue"} · ${j.threads.toFixed(1)} threads, ${num(j.gb, 1)} GB</span>`, stopButton({ pid: j.pid }, commandName(j.command))]));
  }
  if (home?.stop) {
    const source = S.generations.flatMap((G) => G.sources).find((x) => /_homelab$/.test(x.folder) && x.running);
    rows.push(tr([chip("running", "home server"), "Self-play (container)", source ? `${num(source.games)} games, ${num(source.per_hour)} in the last hour` : "", `<span class="muted">${home.jobs[0].status}</span>`, stopButton({ home: true }, "self-play on the home server")]));
  }
  // Queue jobs that aren't a lab command (copying to the drive, a backup...), or are starting
  for (const j of S.jobs.filter((j) => j.status === "running" && !S.compute[0].jobs.some((x) => x.queue_job === j.id)))
    rows.push(tr([chip("running", "laptop"), esc(j.label), "", `<span class="muted">queue, since ${when(j.started)}</span>`, `<button class="stop" data-stop="${j.id}">Stop</button>`]));
  return rows.length ? table(["Where", "What", "Progress", "", ""], rows) : `<p class="muted">Nothing is running.</p>`;
}

// Per machine: its threads as lab / other / idle, what is idle of the threads the loop uses, and the commands running
function compute() {
  return `<div class="grid wide">${S.compute.map((c) => {
    if (!c.reachable && c.name !== "laptop") return `<div class="card"><h3>${esc(c.name)} ${chip("warn", "not reachable")}</h3><p class="muted">No answer over ssh.</p></div>`;
    const other = Math.max(0, c.busy - c.lab), idle = Math.max(0, c.threads - c.busy), free = Math.max(0, Math.min(c.usable, c.threads - c.busy));
    const seg = (n, color, name) => (n > 0.05 ? `<i style="width:${(100 * n) / c.threads}%;background:${color}" data-tip="${name}: ${n.toFixed(1)} threads"></i>` : "");
    return `<div class="card"><h3>${esc(c.name)} ${free >= 1 ? chip("warn", `${Math.floor(free + 0.2)} idle`) : chip("ok", "in use")}</h3>
      <div class="tile"><div class="value">${free.toFixed(1)} idle <span class="muted" style="font-size:14px;font-weight:400">of the ${c.usable} threads the loop uses (${c.threads} in the machine)</span></div></div>
      <div class="meter split">${seg(c.lab, "var(--s1)", "lab")}${seg(other, "var(--neutral)", "everything else")}</div>
      ${legend([[`lab ${c.lab.toFixed(1)}`, "var(--s1)"], [`everything else ${other.toFixed(1)}`, "var(--neutral)"], [`idle ${idle.toFixed(1)}`, "var(--line)"]])}
      ${c.jobs[0]?.status ? `<p class="muted">Self-play container: ${esc(c.jobs[0].status.toLowerCase())}</p>` : ""}</div>`;
  }).join("")}</div>`;
}

function pageNow() {
  const g = S.generation, G = generationData(g);
  const rate = sum(G.sources.map((s) => s.per_hour)), left = Math.max(0, S.target_games - G.games);
  const champion = last(events("verdict").filter((v) => v.result === "promoted"));
  const anchor = champion && last(S.matches.filter((m) => m.role === "anchor_puct" && Object.values(m.nets).includes(champion.net)));
  const a = anchor?.arms[0];
  const feed = [...S.events, ...S.matches.filter((m) => !m.running).map((m) => ({ ...m, kind: "match" }))].sort((x, y) => (x.time < y.time ? 1 : -1)).slice(0, 10);
  return `<h2>Generation ${g}</h2>
    <div class="grid">
      ${tile("Self-play games", num(G.games), left ? `${num(left)} to go of ${num(S.target_games)}` : `target of ${num(S.target_games)} reached`, G.games / S.target_games)}
      ${tile("Pace", rate ? `${num(rate)}/h` : "stopped", rate && left ? `about ${num(left / rate, 1)} h to the target` : `${num(G.worker_hours)} worker-hours so far`)}
      ${tile("Champion policy", champion ? net(champion.net) : "–", champion ? `promoted in generation ${champion.generation}` : "")}
      ${tile("PUCT vs the tree at 2000", a ? pm(a.per_seed_diff, a.per_seed_ci) : "–", a ? `points per game, wins ${pct(a.win_rate)}` : "anchor not played with the champion yet")}
      ${tile("Disk free", `${num(S.disk_free_gb)} GB`, S.disk_free_gb < 40 ? "a training window needs ~35 GB" : "")}
      ${tile("Archive drive", S.drive ? "connected" : "not connected", "")}
    </div>
    <h2>Compute</h2>${compute()}
    <h2>This iteration</h2>${stepper(g)}
    <div class="cols"><section><h2>Running</h2><div class="card">${running()}</div></section>
    <section><h2>Latest</h2><div class="card">${table(["When", "Gen", ""], feed.map((e) => tr([when(e.time), e.generation, describe(e)])))}</div></section></div>`;
}

function pageProgress() {
  const gens = S.generations, hours = {};
  gens.reduce((acc, G) => (hours[G.generation] = acc + G.worker_hours), 0);
  const X = (g) => (xMode === "hours" ? hours[g] : g);
  const xTicks = gens.map((G) => ({ x: X(G.generation), label: xMode === "hours" ? `${num(hours[G.generation])} h` : `gen ${G.generation}` }));
  const over = (name, color, f, tip) => ({ name, color, pts: gens.map((G) => ({ x: X(G.generation), ...f(G.generation) })).map((p) => ({ ...p, tip: p.y == null ? "" : tip(p) })) });
  const anchor = (role) => (g) => { const a = matchOf(role, g)?.arms[0]; return a ? { y: a.per_seed_diff, lo: a.per_seed_diff - a.per_seed_ci, hi: a.per_seed_diff + a.per_seed_ci, win: a.win_rate } : {}; };
  const strength = lineChart({
    xTicks, refs: [{ y: 0, label: "the tree at 2000 simulations" }], yFmt: pts, w: cardW(2), h: 320,
    series: [["PUCT + policy", "var(--s1)", "anchor_puct"], ["policy alone", "var(--s2)", "anchor_policy"]].map(([name, color, role]) =>
      over(name, color, anchor(role), (p) => `${name}: ${pts(p.y)} ± ${(p.hi - p.y).toFixed(1)} points per game\nwins ${pct(p.win)}`)),
  });
  const decisions = newest(gens).map((G) => {
    const m = matchOf("decision", G.generation), a = m?.arms[0], v = last(events("verdict", G.generation));
    return tr([`gen ${G.generation}`, v ? net(v.net) : "–", a ? ">" + pm(a.per_seed_diff, a.per_seed_ci) : ">–", a ? ">" + pct(a.win_rate) : ">–", a ? ">" + num(a.seeds) : ">–",
      v ? chip(v.result) : chip("todo", "open"), m ? `<a href="#match/${matchId(m)}">match</a>` : esc(v?.note ?? "")]);
  });
  const small = (title, f, n) => `<div class="card"><h3>${title}</h3>${lineChart({ xTicks, w: Math.floor((cardW(2) + 34 - 12 * (n - 1)) / n) - 34, h: 200, yFmt: (v) => pct(v), labels: false, series: f })}</div>`;
  const two = (get, a, b) => [over(a, "var(--s1)", (g) => ({ y: get(g)?.[0] }), (p) => `${a}: ${pct(p.y)}`), over(b, "var(--neutral)", (g) => ({ y: get(g)?.[1] }), (p) => `${b}: ${pct(p.y)}`)];
  const policy = [["all", "All decisions"], ["main_turn", "Main turn"], ["play_bird", "Which bird to play"], ["draw_cards", "Draws"]].map(([name, title]) =>
    small(title, two((g) => { const r = vrow(policyOf(g), name); return r && [r.top.net, r.top.kind]; }, "policy net", "kind prior"), 2));
  const pvs = (phase) => (g) => ({ y: last(events("prior_vs_search", g))?.phases.find((p) => p.phase === phase)?.search_keeps_policy_top });
  const value = [["all", "All rounds"], ["r1", "Round 1"], ["r2", "Round 2"], ["r3", "Round 3"], ["r4", "Round 4"]].map(([r, title]) =>
    small(title, two((g) => { const a = vrow(valueOf(g), "all"); return a && [a.net[r].acc, a.line[r].acc]; }, "value net", "score-gap line"), 3));
  const style = newest(gens).map((G) => tr([`gen ${G.generation}`, ...["score", ...SCORE_PARTS, "food left", "decisions"].map((p) => ">" + num(G.parts[p], 1)), ">" + pct(G.wins_first, 1)]));
  return `<div class="cols"><section><h2>Strength</h2>
    <div class="card">
      <div class="actions" style="float:right"><button data-x="generation" class="${xMode === "generation" ? "on" : ""}">by generation</button><button data-x="hours" class="${xMode === "hours" ? "on" : ""}">by self-play worker-hours</button></div>
      <h3>Points per game against the plain tree at 2000 simulations</h3>
      <p class="muted">The anchors: the same opponent and deals every generation, so this is the one chart that compares across generations. Bars are 95% intervals.</p>
      ${legend([["PUCT + policy (equal time)", "var(--s1)"], ["policy alone, no search", "var(--s2)"]])}${strength}
      <h3 style="margin-top:14px">Candidate against champion (PUCT, the promotion decision)</h3>
      ${table(["", "Candidate", ">Points per game", ">Wins", ">Deals", "Verdict", ""], decisions)}
    </div></section>
    <section><h2>How the games look</h2>
    <div class="card"><h3>Mean score in self-play, by where the points come from</h3>${scoreBars(newest(gens), cardW(2))}
      ${table(["", ">score", ...SCORE_PARTS.map((p) => ">" + p), ">food left", ">decisions", ">first player wins"], style)}</div></section></div>
    <div class="cols"><section><h2>${mark("policy")}Policy net</h2>
    <p class="muted">How often its top move is the search's most visited one, on validation deals, against a prior on the kind of move alone. Each generation's targets come from a
      different search, so read the gap to the baseline, not the level across generations.</p>
    ${legend([["policy net", "var(--s1)"], ["kind prior", "var(--neutral)"]])}<div class="grid n2">${policy.join("")}</div>
    <div class="card" style="margin-top:12px"><h3>In self-play, how often the search keeps the policy's top move</h3>
      <p class="muted">Near 90% and rising, with a confident prior, the loop is confirming itself.</p>
      ${legend([["all decisions", "var(--s1)"], ["main turn", "var(--s2)"]])}
      ${lineChart({ xTicks, w: cardW(2), h: 200, yFmt: (v) => pct(v), refs: [{ y: 0.9, label: "alarm" }], series: [over("all", "var(--s1)", pvs("all"), (p) => `all decisions: ${pct(p.y)}`), over("main turn", "var(--s2)", pvs("main_turn"), (p) => `main turn: ${pct(p.y)}`)] })}</div>
    </section><section><h2>${mark("value")}Value net</h2>
    <p class="muted">How often it calls the winner, against a line fitted on the current score gap. Stronger players make closer games, harder to call for any predictor: read the gap to the line.
      None of this says whether it helps the search: the leaf match does (Matches).</p>
    ${legend([["value net", "var(--s1)"], ["score-gap line", "var(--neutral)"]])}<div class="grid n3">${value.join("")}</div></section></div>`;
}

// A training: its window, its error per epoch and its validation table
function trainingCard(e) {
  const policy = e.kind === "train_policy", key = policy ? "ce" : "mse";
  const curve = e.epochs.length
    ? legend([["training", "var(--s2)"], ["validation", "var(--s1)"]]) + lineChart({
        w: 420, h: 180, xTicks: e.epochs.map((_, i) => ({ x: i + 1, label: i + 1 })).filter((t) => e.epochs.length <= 8 || t.x % 2 === 0), yFmt: (v) => v.toFixed(3),
        series: [["training", "var(--s2)", "train_" + key], ["validation", "var(--s1)", "val_" + key]].map(([name, color, k]) => ({ name, color, pts: e.epochs.map((x, i) => ({ x: i + 1, y: x[k], tip: `epoch ${i + 1}, ${name}: ${x[k].toFixed(3)}` })) })),
      })
    : `<p class="muted">No per-epoch record (from ${esc(e.source ?? "before the ledger")}).</p>`;
  const folder = (name) => name in e.window;
  let rows;
  if (policy) {
    const three = (o) => ">" + ["net", "kind", "uniform"].map((k) => (o[k] == null ? "–" : pct(o[k]))).join(" / ");
    rows = table(["Phase or folder", ">Decisions", ">Moves", ">Top move: net / kind / uniform", ">KL: net / kind / uniform"],
      e.validation.map((r, i) => tr([esc(folder(r.name) ? folderName(r.name) : human(r.name)), ">" + num(r.decisions), ">" + num(r.moves, 1), three(r.top), r.kl.net == null ? ">–" : ">" + ["net", "kind", "uniform"].map((k) => r.kl[k].toFixed(2)).join(" / ")],
        folder(r.name) && !folder(e.validation[i - 1].name) ? 'class="sep"' : "")));
  } else {
    const cell = (s) => (s.mse == null ? "" : s.mse.toFixed(3) + " / ") + pct(s.acc);
    rows = table(["Games", ">Positions", "", ">All", ">R1", ">R2", ">R3", ">R4"], e.validation.flatMap((r) => [["value net", r.net], ["score-gap line", r.line]].map(([who, s], k) =>
      tr([k ? "" : esc(folder(r.name) ? folderName(r.name) : human(r.name)), k ? "" : ">" + num(r.positions), `<span class="nowrap">${who}</span>`, ...["all", "r1", "r2", "r3", "r4"].map((x) => ">" + cell(s[x]))], k ? "" : 'class="sep"'))));
  }
  const verdict = events("verdict").find((v) => v.net === e.net), onDisk = S.models.find((m) => m.net === e.net);
  return `<div class="card kind-${policy ? "policy" : "value"}"><h3>${net(e.net)} ${verdict ? chip(verdict.result) : ""} ${onDisk ? chip("ok", "on disk: " + fileName(onDisk.name)) : ""}</h3>
    <p class="muted">${when(e.time)}${e.args?.epochs ? ` · ${e.args.epochs} epochs` : ""} · trained on ${num(sum(Object.values(e.window)))} games:</p>${windowBar(e)}
    <p class="muted">${policy ? "Cross-entropy to the visit shares" : "MSE to the result"}, per epoch</p><div class="side"><div>${curve}</div>${rows}</div></div>`;
}

function trainingCards(g) {
  return `<div class="cols">` + KINDS.map(([kind, title, event]) => {
    const list = newest(events(event, g));
    return `<section><h3 class="group">${mark(kind)}${title}</h3>` + (list.length ? `<div class="grid">${list.map(trainingCard).join("")}</div>` : `<p class="muted">None trained in this generation yet.</p>`) + "</section>";
  }).join("") + "</div>";
}

function matchRows(list) {
  const dom = domain(list.flatMap((m) => m.arms.map((a) => [a.per_seed_diff, a.per_seed_ci])));
  return table(["Match", "For", "Arm", "vs", ">Points per game", "", ">Wins", ">Games", "When"], list.flatMap((m) =>
    (m.arms.length ? m.arms : [{}]).map((a, i) => tr([
      i ? "" : esc(matchTitle(m)) + (m.running ? " " + chip("running") : ""), i ? "" : ROLE[m.role], esc(human(a.arm)), esc(human(a.opponent)), ">" + pm(a.per_seed_diff, a.per_seed_ci),
      forest(a.per_seed_diff, a.per_seed_ci, dom), ">" + pct(a.win_rate), ">" + num(a.games ?? m.games) + (m.running && m.total ? ` / ${num(m.total)}` : ""), i ? "" : when(m.time),
    ], `class="link ${i ? "" : "sep"}" data-href="#match/${matchId(m)}"`))));
}

// Every game on one axis (0 to all games played, by generation), and under it a row per net trained: the
// games in its window
function windowChart() {
  const w = cardW(), l = 190, r = 64, top = 34, rowH = 26, nets = newest(trainings()), total = sum(S.generations.map((G) => G.games));
  const X = (n) => l + (n / total) * (w - l - r), start = {};
  let at = 0, svg = "";
  for (const G of S.generations) {
    start[G.generation] = at;
    svg += `<rect x="${X(at) + 1}" y="16" width="${Math.max(X(at + G.games) - X(at) - 2, 1)}" height="8" rx="3" fill="${genColor(G.generation)}" data-tip="generation ${G.generation}: ${num(G.games)} games"/>` +
      `<text x="${X(at) + 1}" y="11">generation ${G.generation} · ${num(G.games)} games</text>` +
      `<line class="grid-line" x1="${X(at)}" x2="${X(at)}" y1="${top - 6}" y2="${top + nets.length * rowH + 60}"/>`;
    at += G.games;
  }
  let y = top;
  for (const [kind, title, event] of KINDS) {
    const shape = (c) => (kind === "policy" ? `<rect x="1" y="${c - 4}" width="8" height="8" rx="1" transform="rotate(45 5 ${c})" fill="var(--policy)"/>` : `<circle cx="5" cy="${c}" r="4.5" fill="var(--value)"/>`);
    svg += `${shape(y + 9)}<text x="16" y="${y + 13}" style="fill:var(--ink);font-weight:600">${title}</text>`;
    y += 20;
    for (const e of nets.filter((x) => x.kind === event)) {
      const byGen = {};
      for (const [f, n] of Object.entries(e.window)) byGen[folderGeneration(f)] = (byGen[folderGeneration(f)] ?? 0) + n;
      svg += `${shape(y + 11)}<a href="#net/${encodeURIComponent(e.net)}"><text x="16" y="${y + 15}" style="fill:var(--ink);text-decoration:underline">${esc(netName(e))}</text></a><text x="${l - 8}" y="${y + 15}" text-anchor="end">${when(e.time).split(",")[0]}</text>`;
      for (const [g, n] of Object.entries(byGen))
        svg += `<rect x="${X(start[g]) + 1}" y="${y + 4}" width="${Math.max(X(start[g] + n) - X(start[g]) - 2, 1)}" height="14" rx="3" fill="${genColor(+g)}" data-tip="${esc(netName(e))}, trained ${when(e.time)}\n${num(n)} of generation ${g}'s games"/>`;
      svg += `<text x="${w}" y="${y + 15}" text-anchor="end">${num(sum(Object.values(e.window)))}</text>`;
      y += rowH;
    }
    y += 10;
  }
  return `<svg viewBox="0 0 ${w} ${y}" width="${w}">${svg}</svg>`;
}

// Self-play games, whatever nets were trained on them: how they accumulated, when nets were trained, and
// each generation of games with its checks
function pageGames() {
  const gens = S.generations.filter((G) => G.timeline.length);
  const t0 = Math.min(...gens.map((G) => new Date(G.timeline[0][0]).getTime())), H = (iso) => (new Date(iso).getTime() - t0) / 36e5;
  let base = 0, joint = null;
  const series = gens.map((G) => {
    const from = base;
    base += G.games;
    const pts = G.timeline.map(([t, n]) => ({ x: H(t), y: from + n, tip: `${when(t)}: ${num(from + n)} games in all\ngeneration ${G.generation}: ${num(n)}` }));
    if (joint) pts.unshift({ ...joint, tip: "" }); // one unbroken line: flat while nothing was being played
    joint = last(pts);
    return { name: `generation ${G.generation}`, color: genColor(G.generation), dots: false, pts };
  });
  const end = Math.max(...series.flatMap((x) => x.pts.map((q) => q.x))), days = [];
  for (const d = new Date(t0); H(d) <= end; d.setHours(24, 0, 0, 0)) if (H(d) > 0) days.push({ x: H(d), label: d.toLocaleString("en-GB", { day: "numeric", month: "short" }) });
  const usedBy = (g) => newest(trainings()).filter((e) => Object.keys(e.window).some((f) => folderGeneration(f) === g));
  const sign = { ok: "✓ pass", warn: "! look", todo: "not run" };
  const parts = ["score", ...SCORE_PARTS, "food left", "decisions"];
  const cards = S.generations.slice().reverse().map((G) => {
    const g = G.generation, pvs = last(events("prior_vs_search", g)), guide = promoted(g - 1);
    return `<h2>Generation ${g} games</h2>
      <p class="muted">Played by ${g ? `PUCT guided by ${guide ? net(guide.net) : "a policy"}` : "the plain tree (no net)"}.
        ${usedBy(g).length ? "Trained on them: " + KINDS.map(([, , event]) => usedBy(g).filter((e) => e.kind === event).map((e) => net(e.net)).join(", ")).filter(Boolean).join(" · ") + "." : "No net trained on them yet."}</p>
      <div class="grid wide">
        <div class="card"><h3>Checks</h3>${table(["", "", ""], checks(g).filter((c) => c.step === 2).map((c) => tr([chip(c.status, sign[c.status]), c.label, `<span class="muted">${c.detail}</span>`])))}
          <h3 style="margin-top:14px">Sources</h3>${table(["Played on", ">Games", ">Runs", "First game", "Last game", ""], G.sources.map((x) =>
            tr([`<span title="${esc(x.folder)}">${/_homelab$/.test(x.folder) ? "home server" : "laptop"}</span>`, ">" + num(x.games), ">" + x.runs, when(x.first), when(x.last), x.running ? chip("running") : ""])))}</div>
        <div class="card"><h3>Search vs its prior</h3>${pvs
          ? table(["Phase", ">Decisions", ">Search keeps the policy's top", ">Prior on it", ">Visits on it"], pvs.phases.map((q) =>
              tr([esc(human(q.phase)), ">" + num(q.decisions), ">" + pct(q.search_keeps_policy_top), ">" + num(q.prior_on_top, 2), ">" + num(q.visits_on_prior_top, 2)]))) +
            `<p class="muted">${num(pvs.games)} games, guided by ${net(pvs.net)}. Healthy: it disagrees often where the choice matters and sharpens when it agrees (visits above the prior).</p>`
          : `<p class="muted">${g ? "Not run yet (Queue → Search vs prior)." : "No prior: the plain tree."}</p>`}</div>
      </div>`;
  });
  return `<h2>Self-play games</h2>
    <div class="card"><h3>Which games each net was trained on</h3>
      <p class="muted">All games in the order they were played, left to right; a row per net (policy nets, then value nets; newest first), with the part of each generation in its window.
        A window takes a generation's games in file order, so where a partial bar sits inside its generation is only indicative.</p>
      ${windowChart()}</div>
    <div class="card" style="margin-top:12px"><h3>Games collected over time</h3>
      ${legend(series.map((x) => [x.name, x.color]))}${lineChart({ w: cardW(), h: 300, labels: false, yFmt: (v) => num(v), xTicks: days, series })}</div>
    <div class="card" style="margin-top:12px"><h3>How the games look, per generation</h3>
      ${table(["", ">games", ">worker-hours", ...parts.map((q) => ">" + q), ">first player wins"], newest(S.generations).map((G) =>
        tr([`generation ${G.generation}`, ">" + num(G.games), ">" + num(G.worker_hours), ...parts.map((q) => ">" + num(G.parts[q], 1)), ">" + pct(G.wins_first, 1)])))}
      <p class="muted">Scores aren't zero-sum, so stronger play should score more. A part that moves alone (food hoarded, eggs dropped) is a change of style to explain before training on it.</p></div>
    ${cards.join("")}`;
}

// A generation of nets: what was trained in that iteration (each net with its own window of games), the
// checks on the training, the matches and the verdict
function pageGeneration(g) {
  const all = [...new Set([...S.events, ...S.matches].map((e) => e.generation))].sort((x, y) => x - y);
  if (g == null || !all.includes(g)) g = last(all);
  const tabs = all.map((x) => `<button data-href="#gen/${x}" class="${x === g ? "on" : ""}">Generation ${x}</button>`).join("");
  const sign = { ok: "✓ pass", warn: "! look", todo: "not run" };
  const kindOfCheck = (c) => (c.label.startsWith("Policy") ? "policy" : c.label.startsWith("Value") ? "value" : "");
  const matches = newest(S.matches.filter((m) => m.generation === g)), verdicts = newest(events("verdict", g)), training = checks(g).filter((c) => c.step === 5);
  return `<div class="actions" style="margin-top:16px">${tabs}</div>
    <h2>Generation ${g} nets</h2>
    <p class="muted">${verdicts.length ? verdicts.map((v) => `${net(v.net)} ${chip(v.result)} ${esc(v.note ?? "")}`).join(" · ") : "No verdict yet."}</p>
    ${training.length ? `<div class="card"><h3>Checks on the training (of the nets in use)</h3>${table(["", "", ""], training.map((c) => tr([chip(c.status, sign[c.status]), mark(kindOfCheck(c)) + c.label, `<span class="muted">${c.detail}</span>`])))}</div>` : ""}
    ${trainingCards(g)}
    <h2>Matches</h2><div class="card">${matches.length ? matchRows(matches) : `<p class="muted">None yet.</p>`}</div>`;
}

function pageMatches() {
  const gens = [...new Set(S.matches.map((m) => m.generation))].sort((a, b) => b - a);
  return `<h2>Matches</h2><p class="muted">Per-deal score difference with both seats played, 95% interval; the dot is filled when the interval excludes zero. Same axis within a table.</p>` +
    `<div class="cols">` + gens.map((g) => `<section><h3 style="margin-top:18px">Iteration of generation ${g}</h3><div class="card">${matchRows(S.matches.filter((m) => m.generation === g).reverse())}</div></section>`).join("") + "</div>";
}

function pageMatch(id) {
  const m = S.matches.find((x) => x.runs.includes(id));
  if (!m) return `<p class="muted">No such match (its runs may have been pooled differently): <a href="#matches">all matches</a>.</p>`;
  const arms = m.arms.map((a) => {
    const d = a.seed_diffs ?? [];
    let s = 0, s2 = 0;
    const run = d.map((x, i) => { s += x; s2 += x * x; const n = i + 1, mean = s / n, ci = n > 1 ? 1.96 * Math.sqrt(Math.max(0, (s2 - n * mean * mean) / (n - 1)) / n) : 0; return { x: n, y: mean, lo: mean - ci, hi: mean + ci, tip: `after ${n} deals: ${pm(mean, ci)}` }; }).slice(9);
    const mine = m.parts.find((p) => p.arm_label === a.arm), theirs = m.parts.find((p) => p.arm_label === a.opponent);
    const diffs = mine && theirs ? Object.entries(PARTS).map(([name, col]) => [name, mine[col] - theirs[col], mine[col], theirs[col]]) : [];
    const dom = domain(diffs.map(([, v]) => [v, 0]));
    return `<div class="card"><h3>${esc(human(a.arm))} vs ${esc(human(a.opponent))}: ${pm(a.per_seed_diff, a.per_seed_ci)} points per game, wins ${pct(a.win_rate)}</h3>
      <p class="muted">${num(a.games)} games on ${num(a.seeds)} deals${a.s_per_game ? `, ${num(a.s_per_game, 1)} s per game` : ""}</p>
      <div class="side"><div>${run.length ? `<p class="muted">The difference as deals accumulate, with its 95% band: settled once the band stops crossing zero.</p>` +
        lineChart({ w: 520, h: 200, labels: false, yFmt: pts, refs: [{ y: 0, label: "even" }], xTicks: ticks(0, d.length, 5).map((t) => ({ x: t, label: t })), series: [{ name: "mean", color: "var(--s1)", band: true, dots: false, pts: run }] })
        : `<p class="muted">Per-deal differences weren't kept for this match (its result comes from the docs, before the ledger).</p>`}
      </div><div>${diffs.length ? `<h3>Where the points come from</h3>` + table(["", `>${esc(human(a.arm))}`, `>${esc(human(a.opponent))}`, ">difference", ""], diffs.map(([name, v, x, y]) =>
        tr([name, ">" + num(x, 1), ">" + num(y, 1), ">" + pts(v), bar(v, dom, `${name}: ${pts(v)}`)], name === "food left" ? 'class="sep"' : ""))) : ""}</div></div></div>`;
  });
  return `<h2>${esc(matchTitle(m))} ${m.running ? chip("running") : ""}</h2>
    <p>${esc(m.description)}</p>
    <p class="muted">${ROLE[m.role]} · iteration of generation ${m.generation} · ${when(m.time)} · ${num(m.games)}${m.running && m.total ? " / " + num(m.total) : ""} games${m.worker_hours ? ` · ${num(m.worker_hours, 1)} worker-hours` : ""}
      ${Object.entries(m.nets).map(([f, id]) => `· ${esc(fileName(f))}: ${net(id)}`).join(" ")}${m.recorded ? "" : " · not in the ledger (read from its files)"}</p>
    <div class="grid wide">${arms.join("") || `<div class="card"><p class="muted">No finished games to read yet.</p></div>`}</div>
    <details style="margin-top:18px"><summary class="muted">Config and files (${m.runs.length} run${m.runs.length > 1 ? "s" : ""})</summary><pre>${esc(JSON.stringify(m.config, null, 1))}</pre>
      <p class="muted">experiments/data/${esc(m.experiment)}/: ${m.runs.map(esc).join(", ")}</p></details>`;
}

// Everything about one net: where it stands, what it was trained on and how the training went, the games
// it guided, and every match it played
function pageNet(id) {
  const e = trainings().find((x) => x.net === id), policy = e?.kind === "train_policy";
  const verdict = events("verdict").find((v) => v.net === id), onDisk = S.models.filter((m) => m.net === id);
  const played = newest(S.matches.filter((m) => Object.values(m.nets).includes(id)));
  const guided = S.generations.filter((G) => promoted(G.generation - 1)?.net === id);
  const all = e && vrow(e, "all"), anchor = played.find((m) => m.role === "anchor_puct")?.arms[0], alone = played.find((m) => m.role === "anchor_policy")?.arms[0];
  const settings = Object.entries(e?.args ?? {}).filter(([k]) => !["dataset", "out"].includes(k));
  const tiles = !e ? "" : `<div class="grid">
    ${tile("Trained", when(e.time).split(",")[0], `<a href="#gen/${e.generation}">generation ${e.generation} nets</a>`)}
    ${tile("Window", num(sum(Object.values(e.window))), "games")}
    ${policy ? tile("Search's top move", pct(all?.top.net), `kind prior ${pct(all?.top.kind)}, on validation deals`) : tile("Calls the winner", pct(all?.net.all.acc), `score-gap line ${pct(all?.line.all.acc)}, on validation deals`)}
    ${policy ? tile("PUCT vs the plain tree", anchor ? pm(anchor.per_seed_diff, anchor.per_seed_ci) : "–", anchor ? `points per game, wins ${pct(anchor.win_rate)}` : "anchor not played") +
      tile("Alone vs the plain tree", alone ? pm(alone.per_seed_diff, alone.per_seed_ci) : "–", alone ? `points per game, wins ${pct(alone.win_rate)}` : "anchor not played") : ""}
    ${tile("Games it guided", num(sum(guided.map((G) => G.games))), guided.length ? guided.map((G) => `<a href="#games">generation ${G.generation}</a>`).join(", ") : policy ? (verdict?.result === "promoted" ? "none yet: its generation of self-play hasn't started" : "none: not promoted") : "the value net isn't in self-play")}
  </div>`;
  return `<h2>${mark(kindOf(id))}${esc(netText(id))} ${verdict ? chip(verdict.result) : ""} ${onDisk.map((m) => chip("ok", "on disk: " + fileName(m.name))).join(" ")}</h2>
    <p class="muted">${e ? `${policy ? "Policy net" : "Value net"} · file hash ${esc(id)}${e.source ? ` · recorded from ${esc(e.source)}, before the ledger` : ""}${verdict?.note ? " · " + esc(verdict.note) : ""}`
      : `The ledger has no training for this net (file hash ${esc(id)}): it was made before the ledger, or outside lab.`}</p>
    ${tiles}
    ${e ? `<h2>Training</h2>${trainingCard(e)}` : ""}
    ${settings.length ? `<details style="margin-top:10px"><summary class="muted">Training settings</summary>${table(["Setting", "Value"], settings.map(([k, v]) => tr([esc(human(k)), esc(v)])))}</details>` : ""}
    <h2>Matches it played</h2><div class="card">${played.length ? matchRows(played) : `<p class="muted">None recorded.</p>`}</div>`;
}

function pageNets() {
  const flow = S.generations.flatMap((G) => {
    const g = G.generation, p = policyOf(g), v = valueOf(g), a = matchOf("anchor_puct", g)?.arms[0];
    return [`<a class="box" href="#games" style="text-decoration:none"><div class="muted">generation ${g} games</div><strong>${num(G.games)} games</strong><div class="muted">${num(G.worker_hours)} worker-hours</div></a>`,
      `<span class="arrow">→</span>`,
      p || v ? `<div class="box net"><div class="muted"><a href="#gen/${g}">generation ${g} nets</a></div><strong>${p ? net(p.net) : "no policy"}</strong><div>${v ? net(v.net) : "no value net"}</div>
        <div class="muted">${a ? `PUCT ${pm(a.per_seed_diff, a.per_seed_ci)} vs tree` : "no anchor yet"}</div></div>` : `<span class="box muted">nets: not trained yet</span>`,
      `<span class="arrow">→</span>`];
  }).slice(0, -1);
  const trained = (id) => S.events.find((e) => e.net === id && e.kind.startsWith("train"));
  return `<h2>Lineage</h2><p class="muted">Each generation's games train the nets that guide the next generation's search.</p><div class="flow">${flow.join("")}</div>
    <h2>All nets</h2><div class="grid wide">${KINDS.map(([kind, title, event]) => `<div class="card kind-${kind}"><h3>${mark(kind)}${title}</h3>${table(["Net", "Trained", ">Window", kind === "policy" ? ">Top move (kind prior)" : ">Winner (score-gap line)", "", "On disk as"], newest(events(event)).map((e) => {
      const r = vrow(e, "all"), v = events("verdict").find((x) => x.net === e.net);
      return tr([net(e.net), `<span class="nowrap">${when(e.time).split(",")[0]}</span>`, ">" + num(sum(Object.values(e.window))),
        kind === "policy" ? `>${pct(r?.top.net)} (${pct(r?.top.kind)})` : `>${pct(r?.net.all.acc)} (${pct(r?.line.all.acc)})`,
        v ? chip(v.result) : "", S.models.filter((m) => m.net === e.net).map((m) => fileName(m.name)).join(", ")]);
    }))}</div>`).join("")}</div>
    <div class="cols"><section><h2>Nets on disk</h2><div class="card">${table(["In use as", "Net", "Saved", "Trained", ""], S.models.slice().sort((x, y) => kindOf(x.net).localeCompare(kindOf(y.net)) || (x.saved < y.saved ? 1 : -1)).map((m) => { // policies, then value nets
      const t = trained(m.net), v = events("verdict").find((x) => x.net === m.net);
      return tr([`<span title="${esc(m.name)}">${cap(fileName(m.name))}</span>`, net(m.net), when(m.saved), t ? `<a href="#gen/${t.generation}">in generation ${t.generation}</a>` : `<span class="muted">not in the ledger</span>`, v ? chip(v.result) : ""]);
    }))}<p class="muted">A net keeps its name through renames of its file (candidate → champion); hover a name for the file or its hash.</p></div>
    </section><section><h2>Datasets on disk</h2><div class="card">${S.datasets.length ? table(["Dataset", ">Games", ">Decisions", ">Size", "Built", "Window"], S.datasets.slice().sort((x, y) => (x.built < y.built ? 1 : -1)).map((d) =>
      tr([`<span title="experiments/data/datasets/${esc(d.name)}">${cap(human(d.name))}</span>`, ">" + num(d.games), ">" + num(d.decisions), `>${num(d.gb)} GB`, when(d.built), Object.entries(d.window).map(([f, n]) => `${folderName(f)}: ${num(n)}`).join(" · ")]))) : `<p class="muted">None.</p>`}</div></section></div>`;
}

function pageQueue() {
  const byStep = {};
  for (const [id, a] of Object.entries(S.actions)) (byStep[a.step] ??= []).push([id, a]);
  const names = { 2: "Check the data", 3: "Build the window", 4: "Train", 6: "Matches", 7: "Self-play", 8: "Record" };
  const button = ([id, a]) => `<button data-action="${id}" class="${a.confirm ? "confirm" : ""}">${esc(a.label)}</button>`;
  const jobs = S.jobs.slice().reverse().map((j) => tr([chip(j.status), esc(j.label), when(j.started ?? j.created), when(j.ended),
    `<a href="#queue" data-log="${esc(j.log)}">log</a>`, j.status === "running" ? `<button data-stop="${j.id}">Stop (Ctrl+C)</button>` : j.status === "queued" ? `<button data-stop="${j.id}">Cancel</button>` : ""]));
  const logs = [...new Set([...S.jobs.map((j) => j.log), ...S.logs.map((l) => l.name)])].filter((n) => S.logs.some((l) => l.name === n));
  logName ??= logs[0];
  const outside = S.busy.length && !S.jobs.some((j) => j.status === "running");
  return `<div class="cols"><section><h2>Queue</h2>
    ${outside ? `<div class="banner">! Something is running outside the queue (${esc(commandName(S.busy[0]))}). A job started now would share the cores with it.</div>` : ""}
    <p class="muted">Jobs run one at a time and survive closing this page. Actions marked … delete or overwrite something and ask first. Commands are those of docs/SELFPLAY_LOOP.md, for generation ${S.generation}.</p>
    <div class="card">${Object.entries(byStep).map(([step, list]) => `<h3>${step} · ${names[step]}</h3><div class="actions" style="margin-bottom:14px">${list.map(button).join("")}</div>`).join("")}
      <h3>Pipelines: each job starts when the one before succeeds</h3><div class="actions">${Object.entries(S.pipelines).map(button).join("")}</div></div>
    </section><section><h2>Jobs</h2><div class="card">${jobs.length ? table(["", "Job", "Started", "Ended", "", ""], jobs) : `<p class="muted">No jobs yet.</p>`}</div>
    <h2>Log</h2><div class="card"><select id="log-select">${logs.map((n) => `<option value="${esc(n)}" ${n === logName ? "selected" : ""}>${esc(logTitle(n))}</option>`).join("")}</select><pre id="log"></pre></div></section></div>`;
}

// ---------- shell ----------
function render() {
  const [page, arg] = (location.hash.slice(1) || "now").split("/");
  const pages = { now: pageNow, progress: pageProgress, games: pageGames, gen: () => pageGeneration(arg == null ? null : +arg), matches: pageMatches, match: () => pageMatch(arg), net: () => pageNet(decodeURIComponent(arg)), nets: pageNets, queue: pageQueue };
  document.getElementById("main").innerHTML = (pages[page] ?? pageNow)();
  for (const a of document.querySelectorAll("nav a")) a.classList.toggle("on", a.hash === "#" + ({ match: "matches", net: "nets" }[page] ?? page));
  document.getElementById("clock").textContent = "read " + when(S.now);
  if (page === "queue") showLog();
}

async function showLog() {
  const pre = document.getElementById("log");
  if (!pre || !logName) return;
  pre.textContent = await (await fetch("/api/log/" + encodeURIComponent(logName))).text();
  pre.scrollTop = pre.scrollHeight;
}

async function refresh() {
  const text = await (await fetch("/api/overview")).text();
  const changed = text.replace(/"now":"[^"]*"/, "") !== lastText;
  lastText = text.replace(/"now":"[^"]*"/, "");
  S = JSON.parse(text);
  if (changed) render();
  else if (location.hash.startsWith("#queue")) showLog();
}

function ask(title, text, commands, yes, go) {
  const dialog = document.getElementById("confirm");
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-text").textContent = text;
  document.getElementById("confirm-commands").textContent = commands;
  document.getElementById("confirm-yes").textContent = yes;
  dialog.onclose = () => dialog.returnValue === "yes" && go();
  dialog.showModal();
}

function boot() {
  const tip = document.getElementById("tip");
  document.addEventListener("mousemove", (e) => {
    const t = e.target.closest?.("[data-tip]");
    tip.hidden = !t || !t.dataset.tip;
    if (!tip.hidden) {
      tip.textContent = t.dataset.tip;
      tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px";
      tip.style.top = e.clientY + 16 + "px";
    }
  });
  document.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-href],[data-x],[data-action],[data-stop],[data-stop-pid],[data-stop-home],[data-log]");
    if (!t || e.target.closest("a:not([data-log])")) return;
    if (t.dataset.href) location.hash = t.dataset.href;
    if (t.dataset.x) { xMode = t.dataset.x; render(); }
    if (t.dataset.log) { logName = t.dataset.log; render(); }
    if (t.dataset.stop) { await fetch(`/api/jobs/${t.dataset.stop}/stop`, { method: "POST" }); refresh(); }
    if (t.dataset.action) {
      const a = S.actions[t.dataset.action] ?? S.pipelines[t.dataset.action];
      const go = async () => { await fetch("/api/jobs/" + t.dataset.action, { method: "POST" }); refresh(); };
      if (!a.confirm) return go();
      ask(a.label, "This deletes or overwrites something. It will run:", a.commands.join("\n"), "Add to the queue", go);
    }
    if (t.dataset.stopPid || t.dataset.stopHome) {
      const home = t.dataset.stopHome != null;
      ask("Stop " + t.dataset.what, home
        ? "The self-play container stops restarting and gets Ctrl+C: games in flight finish, then it exits. On the home server:"
        : "Ctrl+C: games in flight finish and the files close. Press Stop again to quit at once, losing them. This sends:",
      home ? S.compute.find((c) => c.name === "home server").stop : `SIGINT to process ${t.dataset.stopPid}`, "Stop",
      async () => { const r = await fetch(home ? "/api/stop/home-server" : `/api/stop/laptop/${t.dataset.stopPid}`, { method: "POST" }); if (!r.ok) alert("Not stopped: " + (await r.text())); refresh(); });
    }
  });
  document.addEventListener("change", (e) => { if (e.target.id === "log-select") { logName = e.target.value; showLog(); } });
  addEventListener("hashchange", () => { if (S) { render(); scrollTo(0, 0); } });
  let resized;
  addEventListener("resize", () => { clearTimeout(resized); resized = setTimeout(() => S && render(), 150); });
  refresh();
  setInterval(refresh, 15000);
}

boot();
