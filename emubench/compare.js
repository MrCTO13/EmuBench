// A receipt links one cartridge to one device journal without publishing either identity.
function comparisonKey(run) {
  if (typeof run.comparison_id !== "string" || !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i.test(run.comparison_id) ||
      typeof run.worker_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(run.worker_sha256) ||
      !Number.isInteger(run.rendered_frames) || !Number.isInteger(run.warmup_frames)) return null;
  return JSON.stringify([run.comparison_id,run.submitter,run.os,run.arch,run.cpu,run.profile,run.worker_sha256,run.warmup_frames,run.rendered_frames]);
}
const compareBy = document.getElementById("cohort");
const compareQuery = document.getElementById("compare-query");
const comparePeers = document.getElementById("compare-peers");
const compareBody = document.getElementById("compare-rows");
const compareMessage = document.getElementById("compare-message");
let groups = new Map(), activeGroup = "";
const compareParams = new URLSearchParams(location.search);
const preferredPeers = compareParams.has("emus") ? compareParams.get("emus").split(",") : null;
function fillGroups() {
  const words = key(compareQuery.value).split(" ").filter(Boolean);
  groups = new Map();
  for (const run of runs) {
    const group = comparisonKey(run);
    if (!group) continue;
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(run);
  }
  for (const [id, entries] of groups) {
    if (!entries.some(r => words.every(w => key(r.game).includes(w)))) groups.delete(id);
  }
  compareBy.replaceChildren(...[...groups].map(([id, entries]) => {
    const r = entries[0];
    const label = [r.game, r.cpu || r.arch, r.os, r.warmup_frames + " warm-up + " + r.rendered_frames + " measured",
                   r.comparison_id.slice(0,8) + "/" + r.worker_sha256.slice(0,6)].join(" · ");
    return new Option(label, id);
  }));
  if (groups.has(activeGroup)) compareBy.value = activeGroup;
  compareBy.disabled = !groups.size;
  fillPeers();
}
function fillPeers() {
  const prior = new Map([...comparePeers.querySelectorAll("input")].map(el => [el.value, el.checked]));
  const preserve = activeGroup === compareBy.value;
  activeGroup = compareBy.value;
  const entries = groups.get(activeGroup) || [];
  const expected = entries.length ? entries[0].profile === "snes-boot-no-input-v1" ?
    ["Snes9x", "bsnes", "Carts"] : ["mGBA", "gpSP", "Carts"] : [];
  const seen = new Set([...expected, ...entries.map(r => r.emulator)]);
  comparePeers.replaceChildren(...[...seen].sort().map(name => {
    const label = document.createElement("label"), box = document.createElement("input");
    box.type = "checkbox"; box.value = name; const initial = !preferredPeers || preferredPeers.includes(name);
    box.checked = preserve ? (prior.get(name) ?? initial) : initial;
    label.append(box, " " + name); return label;
  }));
  renderCompared();
}
function renderCompared() {
  const selected = new Set([...comparePeers.querySelectorAll(":checked")].map(el => el.value));
  const entries = groups.get(activeGroup) || [];
  compareBody.replaceChildren();
  for (const run of entries.filter(r => selected.has(r.emulator))) {
    const row = document.createElement("tr");
    for (const value of [run.emulator,run.version,run.average_fps,run.low_1pct_fps,run.high_1pct_fps]) {
      const cell = document.createElement("td");
      cell.textContent = typeof value === "number" ? Math.round(value) : value;
      row.append(cell);
    }
    const cell = document.createElement("td"), link = document.createElement("a");
    link.href = "#run-" + run.number; link.textContent = "FPS trace";
    cell.append(link); row.append(cell); compareBody.append(row);
  }
  const missing = [...selected].filter(name => !entries.some(r => r.emulator === name));
  document.getElementById("missing-peers").textContent = missing.length ? "No matching run for " + missing.join(", ") + "." : "";
  compareMessage.textContent = !entries.length ? (status || "No matched runs for this search. Older submissions can be viewed individually.") :
    !selected.size ? "Select an emulator to compare." : compareBody.children.length + (compareBody.children.length === 1 ? " individual run shown." : " individual runs shown.");
}
compareQuery.addEventListener("input",fillGroups);
compareBy.addEventListener("change",fillPeers);
comparePeers.addEventListener("change",renderCompared);
