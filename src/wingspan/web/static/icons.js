// Game icons from the Wingspan wiki (https://wingspan.miraheze.org), stored in ui/icons/.
const ICONS = new Set([
  "invertebrate", "seed", "fish", "fruit", "rodent", "wild",
  "bowl", "cavity", "ground", "platform", "star",
  "forest", "grassland", "wetland",
  "egg", "card", "die", "predator", "flocking", "points",
]);

function icon(name) {
  return ICONS.has(name) ? `<img class="ico" src="icons/${name}.png" alt="${name}" draggable="false">` : null;
}

// Replace [token] with inline icons; unknown tokens stay as plain words.
function tok(text) {
  const esc = String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return esc.replace(/\[([a-z_ ]+)\]/g, (m, name) => {
    const i = icon(name);
    return i ? `<span class="tok" title="${name}">${i}</span>` : `<b>${name}</b>`;
  });
}

// Blurred silhouettes (viewBox 0 0 100 100) - stand-ins for copyrighted art.
const SILHOUETTES = {
  perched: `<path d="M30 70C20 60 22 40 38 34c2-12 14-18 22-12 6 3 8 6 14 7l-8 4c4 12 0 27-12 35l10 18h-6L48 72l-4 2 2 14h-6V74c-4 0-8-1-10-4z"/><path d="M31 69 11 84l7 2 18-12z"/>`,
  wader: `<path d="M22 50c3-12 26-17 40-11 4-8 2-16 6-22 4-4 10-3 11 1l15 4H79c-5 3-7 11-9 21-4 12-20 16-32 14l-16 6z"/><path d="M46 57l-3 38M55 57l4 38" stroke="currentColor" stroke-width="3"/>`,
  flying: `<path d="M50 44C40 29 20 22 3 26c15 6 25 14 37 26 4 4 8 6 10 10 2-4 6-6 10-10 12-12 22-20 37-26-17-4-37 3-47 18z"/><circle cx="50" cy="40" r="5"/>`,
};

function silhouetteFor(bird) {
  const shape =
    bird.wingspan >= 100 ? "flying"
    : bird.habitats.length === 1 && bird.habitats[0] === "wetland" && bird.wingspan >= 55 ? "wader"
    : "perched";
  return `<svg class="sil" viewBox="0 0 100 100" aria-hidden="true">${SILHOUETTES[shape]}</svg>`;
}

// A player's or bot's picture; without one, their initial on their seat color.
function avatarHtml(p, color, cls = "") {
  const inner = p.avatar ? `<img src="${p.avatar}" alt="" draggable="false">` : (p.initial || (p.name || "?").trim().charAt(0)).toUpperCase();
  return `<span class="av ${cls}" style="--pc:${color}">${inner}</span>`;
}
