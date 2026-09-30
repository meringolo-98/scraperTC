const $ = (sel) => document.querySelector(sel);

const statusLine = $("#status-line");
const results = $("#results");
const stealsList = $("#steals-list");
const listingsList = $("#listings-list");
const huntBtn = $("#hunt-btn");
const demoBtn = $("#demo-btn");
const form = $("#hunt-form");
const queryInput = $("#query");

function money(v) {
  if (typeof v !== "number") return "—";
  return `$${v.toFixed(v >= 100 ? 0 : 2)}`;
}

function setBusy(busy, msg) {
  huntBtn.disabled = busy;
  demoBtn.disabled = busy;
  statusLine.textContent = msg || "";
}

function itemHtml(row, { steal = false } = {}) {
  const defects = (row.defects || []).join(", ") || "none";
  const grade = row.grade_band || "n/a";
  const reason = (row.reasons || [])[0] || row.body || "";
  const badges = [];
  const live = row.extra && (row.extra.live || row.extra.engine === "pricecharting" || row.extra.engine === "live_search");
  if (steal || row.steal_score) badges.push(`<span class="badge steal">steal ${row.score ?? row.steal_score}</span>`);
  if (live || (!row.extra || !row.extra.demo)) badges.push(`<span class="badge">live</span>`);
  if ((row.defects || []).some((d) => String(d).includes("whitening") || String(d).includes("center"))) {
    badges.push(`<span class="badge warn">grade risk</span>`);
  }
  badges.push(`<span class="badge">${row.source || "?"}</span>`);
  const linkLabel = (row.condition === "search") ? "Open live search" : "Open live page";
  return `<li class="item">
    <p class="title">${badges.join("")}${escapeHtml(row.title || row.listing_id || "listing")}</p>
    <p class="meta">${money(row.price_usd ?? row.listed_price)} · grade ${escapeHtml(grade)} · defects ${escapeHtml(defects)}</p>
    <p class="meta">${escapeHtml(reason).slice(0, 180)}</p>
    ${row.url ? `<p class="meta"><a href="${escapeAttr(row.url)}" target="_blank" rel="noopener">${linkLabel}</a></p>` : ""}
  </li>`;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replaceAll("'", "&#39;");
}

function render(payload) {
  const steals = payload.steals || [];
  const items = payload.items || [];
  stealsList.innerHTML = steals.length
    ? steals.map((r) => itemHtml(r, { steal: true })).join("")
    : `<li class="empty">No steal candidates this hunt.</li>`;
  listingsList.innerHTML = items.length
    ? items.map((r) => itemHtml(r)).join("")
    : `<li class="empty">No listings yet.</li>`;
  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runHunt({ demo = false } = {}) {
  const query = queryInput.value.trim();
  if (!demo && !query) {
    statusLine.textContent = "Type a card name first.";
    return;
  }
  setBusy(true, demo ? "Loading demo…" : "Hunting marketplaces…");
  try {
    const res = await fetch("/api/hunt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query || "Charizard Base 4/102",
        demo,
        sites: ["ebay", "tcgplayer", "pricecharting", "mercari"],
      }),
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "hunt failed");
    const n = (data.items || []).length;
    const s = (data.steals || []).length;
    setBusy(false, `${n} listings · ${s} steal${s === 1 ? "" : "s"}`);
    render(data);
  } catch (err) {
    setBusy(false, err.message || "Something broke");
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  runHunt({ demo: false });
});
demoBtn.addEventListener("click", () => runHunt({ demo: true }));

async function boot() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    $("#ver").textContent = data.version || "0.1";
    const keys = [];
    keys.push(data.brave ? "Brave ready" : "PriceCharting + TCG live");
    if (data.ebay) keys.push("eBay API");
    $("#keys").textContent = keys.join(" · ");
    statusLine.textContent = "Type a card and tap Hunt for live links.";
    if (!queryInput.value) {
      queryInput.value = "Charizard Base Set 4/102";
    }
  } catch {
    statusLine.textContent = "Server not reachable.";
  }
}

boot();
