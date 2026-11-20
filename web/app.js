import { Town } from "./town.js";

const $ = (s) => document.querySelector(s);
const money = (n) => (n == null ? "—" : `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const REPLAY = new URLSearchParams(location.search).has("replay");

const town = new Town($("#town"));
let S = null;            // last /api/state
let lastEvent = 0;       // last event id seen
let firstLoad = true;
let viewer = "mom";
const blocked = [];      // blocked attempts (for the ledger)
const searches = {};     // run-scoped search trail per buyer

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

// ---------- tabs ----------
document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== `tab-${b.dataset.tab}`));
  }));

// ---------- state ----------
async function refresh() {
  S = await api(`/api/state?viewer=${viewer}`);
  if (firstLoad) {
    town.setStores(S.stores);
    town.setMembers(S.members);
    const sel = (id) => S.members.map((m) => `<option value="${m.id}">${m.name}${m.role === "parent" ? " (parent)" : ` (${m.age})`}</option>`).join("");
    $("#viewer").innerHTML = sel();
    $("#chatAs").innerHTML = sel();
    $("#viewer").value = viewer;
    $("#chatAs").value = "lucy";
    firstLoad = false;
  }
  renderBadge(); renderPot(); renderLists(); renderLedger(); renderDrills(); renderSql();
  $("#runBtn").disabled = S.run.running;
  $("#runBtn").textContent = S.run.running ? "Elves are shopping…" : "Run the shopping day";
}

function renderBadge() {
  const b = $("#modeBadge");
  const bad = S.policy_mode !== "enforce" || S.skills_version !== "v1";
  b.className = "badge" + (bad ? " warn" : "");
  b.textContent = bad ? `rules: ${S.policy_mode} · skills ${S.skills_version}` : `rules enforced · skills ${S.skills_version}`;
}

// ---------- pot ----------
function renderPot() {
  const isParent = S.viewer?.role === "parent";
  const lock = $("#lock");
  lock.className = "card lock" + (S.pot_unlocked ? " ok" : "");
  lock.innerHTML = S.pot_unlocked
    ? `<div><strong>Pot unlocked</strong><div class="hint" style="margin:0">${S.unlock_via === "persona" ? `A parent passed Persona's check (sandbox)${Object.keys(S.age_verified || {}).length ? ` · 21+ verified: ${Object.keys(S.age_verified).map(name).join(", ")}` : ""}. Elves can check out.` : "Unlocked for the demo without Persona verification."}</div></div><span>✅</span>`
    : `<div><strong>Pot locked</strong><div class="hint" style="margin:0">A parent must verify their identity before any elf can buy.</div></div>
       <button class="primary" id="verifyBtn">${pendingInquiry ? "Check verification" : "Verify parent"}</button>`;
  $("#verifyBtn")?.addEventListener("click", verifyParent);

  const alloc = S.members.reduce((a, m) => a + m.allocation, 0);
  const spent = S.members.reduce((a, m) => a + m.spent, 0);
  $("#potTotal").textContent = money(S.household.pot);
  $("#potAlloc").textContent = money(alloc);
  $("#potSpent").textContent = money(spent);

  const editable = isParent && S.pot_unlocked;
  if (document.activeElement?.type !== "range") {
    $("#sliders").innerHTML = S.members.map((m) => {
      const max = m.cap ?? S.household.pot;
      return `<div class="slider-row ${editable ? "" : "locked"}">
        <div class="who"><strong>${esc(m.name)}</strong><small>${m.role === "parent" ? "parent" : `age ${m.age}`}${m.cap ? ` · cap ${money(m.cap)}` : ""}</small></div>
        <input type="range" min="0" max="${max}" step="10" value="${m.allocation}" data-id="${m.id}" ${editable ? "" : "disabled"} />
        <div class="amt"><strong>${money(m.allocation)}</strong><small>${money(m.remaining)} left</small></div></div>`;
    }).join("");
    document.querySelectorAll("#sliders input").forEach((inp) => {
      inp.addEventListener("input", () => (inp.parentElement.querySelector(".amt strong").textContent = money(inp.value)));
      inp.addEventListener("change", async () => {
        try { await api("/api/allocations", { method: "POST", body: JSON.stringify({ actor: viewer, allocations: { [inp.dataset.id]: Number(inp.value) } }) }); }
        catch (e) { toast(e.message, "blocked"); }
        refresh();
      });
    });
  }
  const pending = S.purchases.filter((p) => p.status === "pending_approval");
  $("#approvals").innerHTML = pending.length ? `<h3 style="font-size:15px;margin:12px 0 6px">Waiting for a parent</h3>` + pending.map((p) =>
    `<div class="card approve-row"><div><strong>${esc(name(p.buyer))}'s elf</strong> wants to buy <strong>${esc(p.item)}</strong> (${money(p.price)}) for ${esc(p.recipient_name)}</div>
     ${isParent ? `<button data-pid="${p.id}">Approve</button>` : `<span class="hint">parent only</span>`}</div>`).join("") : "";
  document.querySelectorAll("#approvals button").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/approve/${b.dataset.pid}`, { method: "POST", body: JSON.stringify({ actor: viewer, approve: true }) });
    refresh();
  }));
}

let pendingInquiry = null;
async function verifyParent() {
  if (S.viewer?.role !== "parent") return toast("Switch 'View as' to Mom or Dad to verify.", "pending");
  try {
    const cfg = await api("/api/persona/config");
    if (cfg.relay) {
      if (!pendingInquiry) {
        const r = await api("/api/persona/relay/start", { method: "POST", body: JSON.stringify({ actor: viewer }) });
        pendingInquiry = r.id;
        window.open(r.url, "_blank", "noopener,noreferrer");
        toast(`Persona Relay <strong>Age 21+</strong> check opened in a new tab. Finish it, then press "Check verification".`, "pending");
        $("#verifyBtn").textContent = "Check verification";
        return;
      }
      const done = await api("/api/persona/relay/check", { method: "POST", body: JSON.stringify({ actor: viewer, relay_id: pendingInquiry }) });
      pendingInquiry = null;
      if (done.claim?.claim_result === "passed") toast(`Persona Relay: <strong>${esc(done.claim.claim_type)}</strong> passed${done.claim.sandbox ? " (sandbox)" : ""}. Pot unlocked.`);
      else toast(`Persona Relay: ${esc(done.claim?.claim_result || done.claim?.error || "not passed")}`, "blocked");
      return refresh();
    }
    if (!cfg.enabled) {
      if (confirm("Persona isn't configured on this server. Unlock without verification (labeled as such in the ledger)?"))
        await api("/api/unlock", { method: "POST", body: JSON.stringify({ actor: viewer, via: "demo-no-persona" }) });
      return refresh();
    }
    if (!pendingInquiry) {
      const r = await api("/api/persona/inquiry", { method: "POST", body: JSON.stringify({ actor: viewer }) });
      pendingInquiry = r.inquiry_id;
      window.open(r.url, "_blank", "width=480,height=760");
      toast(`Persona inquiry <strong>${esc(r.inquiry_id)}</strong> opened. Finish it, then press "Check verification".`, "pending");
      $("#verifyBtn").textContent = "Check verification";
      return;
    }
    const done = await api("/api/persona/complete", { method: "POST", body: JSON.stringify({ actor: viewer, inquiry_id: pendingInquiry }) });
    if (done.pot_unlocked) { pendingInquiry = null; toast("Persona verified. Pot unlocked."); }
    else toast(`Persona status: ${esc(done.status)}. Finish the flow, then check again.`, "pending");
    refresh();
  } catch (e) { toast(esc(e.message), "blocked"); }
}

async function renderSql() {
  try {
    const d = await api("/api/ledger-sql");
    $("#sqlCard").innerHTML = `<div class="card"><div class="label">Live from the ledger · ${d.backend === "singlestore" ? "SingleStore" : "SQLite (local)"}</div>` +
      d.queries.map((q) => `<h3 style="font-size:14px;margin:8px 0 4px">${esc(q.title)}</h3>
        <table class="sqlt">${q.rows.length ? `<tr>${Object.keys(q.rows[0]).map((k) => `<th>${esc(k)}</th>`).join("")}</tr>` +
          q.rows.map((r) => `<tr>${Object.values(r).map((v) => `<td>${esc(typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : v)}</td>`).join("")}</tr>`).join("") : "<tr><td class='hint'>no rows yet</td></tr>"}</table>
        <details><summary>SQL</summary><pre>${esc(q.sql)}</pre></details>`).join("") + `</div>`;
  } catch (e) { /* ignore */ }
}

// ---------- lists ----------
function renderLists() {
  const claimedFor = {};
  for (const p of S.purchases) if (!p.hidden && ["completed", "pending_approval"].includes(p.status)) (claimedFor[p.recipient_id] ||= []).push(p);
  $("#lists").innerHTML = S.members.map((m) => {
    const notes = S.lists[m.id] || [];
    const claimed = m.id === viewer ? [] : claimedFor[m.id] || [];
    const own = m.id === viewer;
    return `<div class="card list-card"><h3>${esc(m.name)}'s list</h3>
      ${notes.length ? `<ul>${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : `<div class="hint">Nothing yet. Chat with ${esc(m.name)}'s elf.</div>`}
      ${claimed.length ? `<div class="claimed">Claimed: ${claimed.map((p) => `${esc(p.item)} (by ${esc(name(p.buyer))})`).join(", ")}</div>` : ""}
      ${own ? `<div class="hint" style="margin:6px 0 0">Gifts for you stay secret.</div>` : ""}</div>`;
  }).join("");
}

$("#chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#chatInput").value.trim();
  if (!msg) return;
  const who = $("#chatAs").value;
  $("#chatInput").value = "";
  $("#chatLog").insertAdjacentHTML("beforeend", `<div class="me">${esc(name(who))}: ${esc(msg)}</div>`);
  town.say(who, "listening…");
  try {
    const r = await api(`/api/chat/${who}`, { method: "POST", body: JSON.stringify({ message: msg, session: "ui" }) });
    $("#chatLog").insertAdjacentHTML("beforeend", `<div class="elf">${esc(r.reply)}</div>`);
  } catch (err) { $("#chatLog").insertAdjacentHTML("beforeend", `<div class="elf bad">${esc(err.message)}</div>`); }
  $("#chatLog").scrollTop = 1e9;
  town.say(who, "");
  refresh();
});

// ---------- ledger ----------
const VENDOR = { senso: "Senso", cognee: "Cognee", local: "Memory (local)", policy: "Household rules", statsig: "Statsig",
  "local-default": "Gate (default)", persona: "Persona", ledger: "Ledger", singlestore: "SingleStore" };
const chip = (v) => `<span class="chip ${esc(v)}">${esc(VENDOR[v] || v)}</span>`;

function renderLedger() {
  const v = S.viewer;
  const cards = S.purchases.slice().reverse().map((p) => {
    if (p.hidden) {
      return `<div class="card receipt"><div class="head"><div><div class="item">🎁 ${esc(p.item)}</div>
        <div class="meta">From ${esc(name(p.buyer))}'s elf · ${esc(p.store)} · receipt ${esc(p.receipt || "pending")}</div></div>
        <span class="status ${p.status}">${p.status.replace("_", " ")}</span></div></div>`;
    }
    const ev = p.evidence || {};
    const steps = [];
    if (ev.memory) steps.push(`<li>${chip(ev.memory.backend)}<span>Recalled ${esc(p.recipient_name)}'s list: ${esc((ev.memory.answer || (ev.memory.notes || []).join("; ")).slice(0, 220))}</span></li>`);
    const sr = (ev.senso_results || [])[0] || [];
    if (sr.length) steps.push(`<li>${chip("senso")}<span>Searched the trusted catalog: ${sr.length} passages · top "${esc(sr[0].title)}" (content ${esc((sr[0].content_id || "").slice(0, 8))}…, score ${Number(sr[0].score || 0).toFixed(2)})</span></li>`);
    if (ev.fact_check) {
      const fc = ev.fact_check;
      const verdicts = (fc.claims || []).map((c) => `${c.verdict || "–"}`).join(", ");
      steps.push(`<li>${chip("senso")}<span>Fact-checked the elf's claim "${esc(ev.claim)}" → <strong class="${fc.overall === "conflict" ? "bad" : fc.overall === "verified" ? "ok" : ""}">${esc(fc.overall)}</strong>${verdicts ? ` (${esc(verdicts)})` : ""}</span></li>`);
    }
    if (ev.policy) steps.push(`<li>${chip("policy")}<span>${ev.policy.checks.map((c) => `<span class="${c.ok ? "ok" : "bad"}">${c.ok ? "✓" : "✗"}</span> ${esc(c.name.replace("_", " "))}`).join(" · ")}</span></li>`);
    if (ev.gate) steps.push(`<li>${chip(ev.gate.source === "statsig" ? "statsig" : "local-default")}<span>Gate teen_needs_parent_approval = ${ev.gate.teen_needs_parent_approval}</span></li>`);
    steps.push(`<li>${chip(S.ledger_backend === "singlestore" ? "singlestore" : "ledger")}<span>${p.status === "completed" ? `Simulated checkout · receipt ${esc(p.receipt)}` : p.status === "pending_approval" ? "Held for parent approval" : esc(p.status)}</span></li>`);
    return `<div class="card receipt"><div class="head"><div><div class="item">${esc(p.item)} <span class="meta">(${esc(p.sku)})</span></div>
      <div class="meta">${esc(name(p.buyer))}'s elf → ${esc(p.recipient_name)} · ${esc(p.store)} · ${money(p.price)}</div></div>
      <span class="status ${p.status}">${p.status.replace("_", " ")}</span></div>
      <div class="meta" style="margin-top:4px">Why: ${esc(ev.reason)}</div>
      <ul class="steps">${steps.join("")}</ul>
      <details><summary>Raw evidence</summary><pre>${esc(JSON.stringify(ev, null, 2))}</pre></details></div>`;
  });
  const blockedCards = v?.role === "parent" ? blocked.slice().reverse().map((b) =>
    `<div class="card receipt"><div class="head"><div><div class="item block-label">⛔ ${esc(b.label || "Attempt blocked")}</div>
     <div class="meta">${esc(name(b.actor))}'s elf tried ${esc(b.item || b.sku)}${b.price ? ` (${money(b.price)})` : ""} for ${esc(b.recipient)} · ${esc(b.store_name || "")}</div></div><span class="status blocked">blocked</span></div>
     <div class="meta bad" style="margin-top:4px">${esc(b.reason)}</div></div>`) : [];
  $("#ledger").innerHTML = cards.concat(blockedCards).join("") || `<div class="hint">No receipts yet. Press "Run the shopping day".</div>`;
}

// ---------- drills ----------
let drills = null;
async function renderDrills() {
  if (drills === null) {
    drills = await fetch("/web/drills.json").then((r) => (r.ok ? r.json() : false)).catch(() => false);
  }
  if (!drills) {
    $("#drills").innerHTML = `<div class="card"><h3>Firedrill</h3><p class="hint">Simulated family members (a pushy 14-year-old, an over-budget shopper, an off-list friend) drill the elves through <code>POST /chat/{member}</code>. Results appear here after a run.</p></div>`;
    return;
  }
  $("#drills").innerHTML = `<p class="hint">${esc(drills.note)}</p>` + drills.runs.map((run) => `<h3 style="font-size:16px;margin:10px 0 6px">${esc(run.title)}</h3>` +
    run.drills.map((d) => `<div class="card drill ${d.pass ? "pass" : d.status === "fail" ? "fail" : ""}">
      <div class="head" style="display:flex;justify-content:space-between;gap:8px"><strong>${esc(d.scenario)}</strong>
      <span class="status ${d.pass ? "completed" : d.status === "fail" ? "blocked" : "pending_approval"}">${esc(d.status)} · ${esc(d.score)}</span></div>
      ${d.transcript?.length ? `<details><summary>Conversation (${d.transcript.length} turns)</summary><pre>${esc(d.transcript.join("\n\n"))}</pre></details>` : ""}
      </div>`).join("")).join("") +
    (drills.diff ? `<details><summary>What changed between runs (skills.md diff)</summary><pre>${esc(drills.diff)}</pre></details>` : "");
}

// ---------- events → town ----------
function name(id) { return S?.members.find((m) => m.id === id)?.name || id; }

function toast(text, kind = "") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.innerHTML = text;
  $("#toasts").prepend(t);
  setTimeout(() => t.remove(), 6500);
  while ($("#toasts").children.length > 5) $("#toasts").lastChild.remove();
}

function handle(e, animate) {
  const d = e.data || {};
  if (e.kind === "walk") { town.reveal(d.store); if (animate) { town.walkTo(e.actor, d.store); town.say(e.actor, d.why === "buying" ? `heading into ${d.store_name}` : `browsing ${d.store_name}`); } }
  if (!animate) { if (e.kind === "blocked") blocked.push({ ...d, actor: e.actor }); return; }
  if (e.kind === "recall") town.say(e.actor, `reading ${d.person}'s list`);
  if (e.kind === "fact_check") town.say(e.actor, `fact-check: ${d.overall}`);
  if (e.kind === "policy") town.say(e.actor, d.allowed ? "rules ✓" : "rules ✗");
  if (e.kind === "purchase") {
    town.reveal(d.store);
    const pending = d.status === "pending_approval";
    toast(`<strong>${esc(name(e.actor))}'s elf</strong> ${pending ? "wants to buy something at" : "just bought something at"} <strong>${esc(d.store_name)}</strong>${pending ? " (waiting for a parent)" : ""}`, pending ? "pending" : "");
    town.say(e.actor, pending ? "waiting for a parent" : "🎁 bought a gift!");
    town.goHome(e.actor);
  }
  if (e.kind === "blocked") {
    blocked.push({ ...d, actor: e.actor });
    toast(`<strong>${esc(name(e.actor))}'s elf</strong> was stopped by a household rule${d.store_name ? ` at <strong>${esc(d.store_name)}</strong>` : ""}`, "blocked");
    town.say(e.actor, "stopped by a rule");
  }
  if (e.kind === "wish_saved") town.say(e.actor, "added to the list ✍");
  if (e.kind === "pot_unlocked") toast(`<strong>${esc(name(e.actor))}</strong> verified with Persona. The pot is unlocked.`);
  if (e.kind === "run_end") Object.keys(town.elves).forEach((id) => { town.goHome(id); setTimeout(() => town.say(id, ""), 4000); });
}

async function pollEvents() {
  try {
    const { events } = await api(`/api/events?since=${lastEvent}`);
    const animate = lastEvent > 0 || events.length === 0 ? true : false;
    for (const e of events) handle(e, animate || lastEvent > 0);
    if (events.length) { lastEvent = events[events.length - 1].id; await refresh(); }
    if (lastEvent === 0) lastEvent = -1; // mark "history loaded"
  } catch (err) { /* server restarting */ }
  setTimeout(pollEvents, 700);
}

// ---------- demo menu ----------
api("/api/playbooks").then(({ playbooks }) => {
  $("#playbooks").innerHTML = playbooks.map((p) => `<button class="pb" data-pb="${p.id}"><span>${esc(p.title)}</span><small>${esc(p.expected)}</small></button>`).join("");
  document.querySelectorAll("[data-pb]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/playbook/${b.dataset.pb}`, { method: "POST" });
    toast(`Forced: ${esc(b.querySelector("span").textContent)}`, "pending");
    document.querySelector(".demo-menu").open = false;
  }));
});
document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", async () => {
  const before = b.dataset.mode === "before";
  await api("/api/mode", { method: "POST", body: JSON.stringify({ policy_mode: before ? "log" : "enforce", skills_version: before ? "v0" : "v1" }) });
  toast(before ? "Before mode: thin skills, rules only logged" : "After mode: full skills, rules enforced", before ? "blocked" : "");
  refresh();
}));

// ---------- controls ----------
$("#viewer").addEventListener("change", (e) => { viewer = e.target.value; refresh(); });
$("#runBtn").addEventListener("click", async () => {
  if (!S.pot_unlocked) return toast("The pot is locked. A parent must verify first (Family Pot tab).", "blocked");
  await api("/api/run-day", { method: "POST" });
  refresh();
});
$("#resetBtn").addEventListener("click", async () => {
  if (!confirm("Reset the demo ledger? (Christmas lists are kept.)")) return;
  await api("/api/reset", { method: "POST", body: JSON.stringify({ keep_lists: true }) });
  location.reload();
});

await refresh();
pollEvents();
setInterval(refresh, 4000);
