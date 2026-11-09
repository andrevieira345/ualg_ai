// Heredity live
//   GET  /api/families        -> lista de familias csv
//   GET  /api/family/<file>   -> people, layout, default mutation
//   POST /api/infer           -> probabilidades


const CARD_W = 232, COL = 262, ROW = 300;
let family = null, evidence = {}, original = {}, previous = null, mutation = 0.01, timer = null;

const $ = id => document.getElementById(id);
const pct = p => (p * 100).toFixed(1) + "%";

async function api(path, body) {
  const r = await fetch(path, body ? {method: "POST", headers: {"Content-Type": "application/json"},
                                      body: JSON.stringify(body)} : {});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "request failed");
  return data;
}

async function init() {
  const families = await api("/api/families");
  $("family").innerHTML = families.map(f => `<option>${f}</option>`).join("");
  $("family").onchange = () => loadFamily($("family").value);
  $("mutation").oninput = () => { mutation = +$("mutation").value; showMutation(); schedule(); };
  $("reset").onclick = () => loadFamily(family.file);
  if (families.length) loadFamily(families[0]);
  else status("No family CSVs found in data/", true);
}

function showMutation() { $("mutationVal").textContent = mutation.toFixed(3); }
function status(text, err) { $("status").textContent = text; $("status").classList.toggle("err", !!err); }

async function loadFamily(file) {
  family = await api("/api/family/" + encodeURIComponent(file));
  evidence = {}; original = {}; previous = null;
  family.people.forEach(p => {
    evidence[p.name] = {trait: p.trait, gene: null};
    original[p.name] = {trait: p.trait, gene: null};
  });
  mutation = family.mutation;
  $("mutation").value = mutation; showMutation();
  drawTree();
  if (family.tooBig) { status(`${family.people.length} people: too many for live inference`, true); return; }
  infer();
}

function drawTree() {
  const tree = $("tree");
  const cols = family.people.map(p => p.pos[0]), rows = family.people.map(p => p.pos[1]);
  const minC = Math.min(...cols), maxC = Math.max(...cols), maxR = Math.max(...rows);
  const width = (maxC - minC) * COL + CARD_W, height = maxR * ROW + 270;
  tree.style.width = width + "px"; tree.style.height = height + "px";
  const x = p => (p.pos[0] - minC) * COL, y = p => p.pos[1] * ROW;
  const byName = Object.fromEntries(family.people.map(p => [p.name, p]));

  // lines: parents -> children
  let paths = "";
  const fams = {};
  family.people.forEach(p => { if (p.mother) (fams[p.mother + "|" + p.father] ||= []).push(p); });
  for (const key in fams) {
    const [m, f] = key.split("|").map(n => byName[n]), kids = fams[key];
    const mx = (x(m) + x(f)) / 2 + CARD_W / 2, top = y(m) + 120;
    if (y(m) === y(f)) {
      const l = Math.min(x(m), x(f)) + CARD_W, r = Math.max(x(m), x(f));
      paths += `<path d="M${l},${top} H${r}"/>`;
    }
    const mid = y(kids[0]) - 24, xs = kids.map(k => x(k) + CARD_W / 2).concat([mx]);
    paths += `<path d="M${mx},${top} V${mid} M${Math.min(...xs)},${mid} H${Math.max(...xs)}"/>`;
    kids.forEach(k => paths += `<path d="M${x(k) + CARD_W / 2},${mid} V${y(k)}"/>`);
  }
  tree.innerHTML = `<svg class="lines" width="${width}" height="${height}">${paths}</svg>`;

  family.people.forEach(p => {
    const card = document.createElement("div");
    card.className = "card"; card.id = "card-" + p.name;
    card.style.left = x(p) + "px"; card.style.top = y(p) + "px";
    card.innerHTML = `
      <h2>${p.name}<small>${p.mother ? "child of " + p.mother + " & " + p.father : "no parents in data"}</small></h2>
      <div class="row">Trait <span class="seg" data-kind="trait">
        <button data-v="true">Has</button><button data-v="false">No</button><button data-v="null">?</button></span></div>
      <div class="row">Genes <span class="seg" data-kind="gene">
        <button data-v="null">?</button><button data-v="0">0</button><button data-v="1">1</button><button data-v="2">2</button></span></div>
      <div class="res" id="res-${p.name}"></div>`;
    card.querySelectorAll(".seg").forEach(seg => seg.addEventListener("click", e => {
      if (e.target.tagName !== "BUTTON") return;
      evidence[p.name][seg.dataset.kind] = JSON.parse(e.target.dataset.v);
      refreshControls(); schedule(0);
    }));
    tree.appendChild(card);
  });
  refreshControls();
}

function refreshControls() {
  family.people.forEach(p => {
    const card = $("card-" + p.name), ev = evidence[p.name], og = original[p.name];
    card.querySelectorAll(".seg").forEach(seg => seg.querySelectorAll("button").forEach(b =>
      b.classList.toggle("on", JSON.parse(b.dataset.v) === ev[seg.dataset.kind])));
    card.classList.toggle("changed", ev.trait !== og.trait || ev.gene !== og.gene);
  });
}

function schedule(delay = 120) { clearTimeout(timer); timer = setTimeout(infer, delay); }

async function infer() {
  if (!family || family.tooBig) return;
  $("tree").classList.add("busy"); status("Calculating…");
  try {
    const data = await api("/api/infer", {file: family.file, evidence, mutation});
    showResults(data.results);
    status(`Updated in ${data.ms} ms`);
  } catch (e) {
    status(e.message, true);
  } finally {
    $("tree").classList.remove("busy");
  }
}

function deltaHtml(now, before) {
  if (before === undefined) return `<span class="delta"></span>`;
  const d = (now - before) * 100;
  if (Math.abs(d) < 0.05) return `<span class="delta"></span>`;
  return `<span class="delta ${d > 0 ? "up" : "down"}">${d > 0 ? "+" : ""}${d.toFixed(1)}</span>`;
}

function barHtml(label, p, before, colour) {
  return `<div class="bar"><span>${label}</span>
    <div class="track"><div class="fill" style="width:${p * 100}%;background:${colour}"></div></div>
    <span class="num">${pct(p)}</span>${deltaHtml(p, before)}</div>`;
}

function showResults(results) {
  family.people.forEach(p => {
    const r = results[p.name], prev = previous && previous[p.name];
    $("res-" + p.name).innerHTML =
      barHtml("Has trait", r.trait, prev && prev.trait, "var(--trait)") +
      barHtml("0 genes", r.gene["0"], prev && prev.gene["0"], "var(--g0)") +
      barHtml("1 gene", r.gene["1"], prev && prev.gene["1"], "var(--g1)") +
      barHtml("2 genes", r.gene["2"], prev && prev.gene["2"], "var(--g2)");
  });
  previous = results;
}

init().catch(e => status(e.message, true));