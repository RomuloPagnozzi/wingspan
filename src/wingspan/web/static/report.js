"use strict";

// "Report a bug": the player's note, saved with where they were (game id + move number), so the
// exact moment can be reopened later with `make debug ID=<game> AT=<move>`.
let reportContext = {};

function openReport(context = {}) {
  reportContext = context;
  const el = document.querySelector("#report");
  el.innerHTML = `<div class="sheet name-sheet"><h2>Report a bug</h2>
    <p>What happened, and what did you expect?${context.game ? " This exact moment of the game is saved with your report." : ""}</p>
    <textarea id="report-text" maxlength="4000" rows="6" placeholder="e.g. I picked the fish but got a seed"></textarea>
    <p class="err" id="report-err"></p>
    <div class="m-foot"><button class="ghost" data-report="cancel">Cancel</button><button class="primary" data-report="send">Send report</button></div></div>`;
  el.hidden = false;
  document.querySelector("#report-text").focus();
}

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-report]");
  if (!btn) return;
  const el = document.querySelector("#report");
  if (btn.dataset.report === "cancel") return (el.hidden = true);
  const text = document.querySelector("#report-text").value.trim();
  if (!text) return (document.querySelector("#report-err").textContent = "Tell us what happened first.");
  btn.disabled = true;
  const r = await fetch("/api/reports", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, ...reportContext }) });
  if (!r.ok) {
    btn.disabled = false;
    return (document.querySelector("#report-err").textContent = "Couldn't send it; try again in a moment.");
  }
  el.innerHTML = `<div class="sheet name-sheet"><h2>Thanks!</h2><p>Your report is saved${reportContext.game ? " with this moment of the game" : ""}.</p>
    <div class="m-foot"><div></div><button class="primary" data-report="cancel">Close</button></div></div>`;
});
