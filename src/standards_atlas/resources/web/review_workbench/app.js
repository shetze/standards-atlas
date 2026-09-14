import {dateText, element, labelled, labels, option, predicateText, statuses, valueText} from "./format.js";
import {predicateEditor} from "./editors.js";

const $ = id => document.getElementById(id);
const S = {csrf: "", handle: "", reviewer: "", package: null, page: null, current: null,
  cards: [], offset: 0, busy: false, filters: null, assessmentDirty: false};
function base() {return `/api/packages/${encodeURIComponent(S.handle)}`;}
function dirty() {return S.assessmentDirty || S.cards.some(card => card.status.value !== "" || card.hasNote?.());}
function assertActiveIdentity() {
  if ($("reviewer").value.trim() !== S.reviewer || $("packageSelect").value !== S.handle) {
    throw new Error("Reviewer oder Paket wurde geändert. Zuerst ‚Paket öffnen / fortsetzen‘ wählen; der angezeigte Review gehört noch zur bisherigen Identität.");
  }
}
function leave() {return !dirty() || window.confirm("Ungespeicherte Entscheidungen / Ersteinschätzung verwerfen?");}
function notice(text) {$("notice").textContent = text;}
function showError(error) {
  $("error").hidden = false;
  $("error").textContent = error.message || String(error);
  $("error").scrollIntoView({block: "nearest"});
}
async function api(path, payload) {
  const config = payload === undefined ? {} : {method: "POST", headers: {
    "Content-Type": "application/json", "X-Atlas-CSRF": S.csrf}, body: JSON.stringify(payload)};
  const response = await fetch(path, {...config, cache: "no-store", credentials: "same-origin"});
  let data;
  try {data = await response.json();} catch {throw new Error(`HTTP ${response.status}: keine gültige Serverantwort.`);}
  if (!response.ok) {
    const details = (data.details || []).map(d => `${d.loc.join(".")}: ${d.msg}`).join("\n");
    const suffix = response.status === 409
      ? "\nDer Reviewstand wurde geändert. Deine Eingaben bleiben sichtbar; bitte bewusst aktualisieren und erneut prüfen." : "";
    throw new Error(`${data.error || `HTTP ${response.status}`}\n${details}${suffix}`);
  }
  return data;
}
async function run(task) {
  if (S.busy) return;
  S.busy = true; document.body.dataset.busy = "true";
  $("error").hidden = true;
  const controls = [...document.querySelectorAll("button,input,select,textarea")].map(n => [n, n.disabled]);
  controls.forEach(([n]) => {n.disabled = true;});
  try {await task();} catch (error) {showError(error);}
  finally {
    controls.forEach(([n, disabled]) => {if (n.isConnected) n.disabled = disabled;});
    S.busy = false; document.body.dataset.busy = "false";
    updateDirty(); updatePagination();
  }
}
function updateDirty() {
  const count = S.cards.filter(c => c.status.value).length;
  $("dirtyStatus").textContent = count ? `${count} ausgewählte Entscheidung(en), noch nicht gespeichert.`
    : S.cards.some(c => c.hasNote?.()) ? "Ungespeicherte Notiz ohne ausgewählte Entscheidung."
    : "Keine ungespeicherten Entscheidungen.";
}
function updatePagination() {
  if (S.page) {
    $("prevPage").disabled = S.offset === 0;
    $("nextPage").disabled = S.page.next_offset === null;
  }
}
function fillSelect(node, choices, allText, current = "") {
  node.replaceChildren(option("", allText));
  choices.forEach(([value, text]) => node.append(option(value, text)));
  node.value = current;
}
function renderOverview() {
  const {report, profile, rules} = S.package;
  $("coverage").replaceChildren();
  for (const split of ["development", "holdout"]) {
    const data = report.splits[split];
    const card = element("section", null, "panel coverage-card");
    const totalAttrs = data.selected_cases * profile.attributes.length;
    const confirmed = Object.values(data.confirmed_attributes).reduce((a, b) => a + b, 0);
    const progress = element("progress"); progress.max = Math.max(data.selected_cases, 1);
    progress.value = data.complete_cases; progress.setAttribute("aria-label", `${split}: vollständig bestätigte Fälle`);
    card.append(element("h3", split === "holdout" ? "Holdout · getrennte Auswahl" : "Development · bekannter Bestand"),
      element("strong", `${data.complete_cases} / ${data.selected_cases} Fälle vollständig`), progress,
      element("p", `${confirmed} / ${totalAttrs} Attribute bestätigt. Offene Fälle zählen nicht als negative Annotation.`, "muted"));
    $("coverage").append(card);
  }
  const reportBox = $("report"); reportBox.replaceChildren();
  reportBox.append(element("p", report.ready_for_publication
    ? "Fachliche Vollständigkeitsprüfung erfüllt. Veröffentlichung und Prüfung gegen aktuelle Quellen erfolgen weiterhin über den CLI-Import."
    : `${report.unresolved.length} offene Attribute · ${report.coverage_gaps.length} Abdeckungslücken · ${report.conflicts.length} fachliche Widersprüche.`));
  reportBox.append(element("p", "Die Anzeige prüft das eingefrorene Paket; sie behauptet keine unveränderten Live-Quellen oder unabhängige bisherige Nutzung des Holdouts.", "muted"));
  const details = element("details"); details.append(element("summary", "Vollständiger Abdeckungsbericht"),
    element("pre", JSON.stringify(report, null, 2))); reportBox.append(details);
  $("rules").replaceChildren();
  for (const [name, text] of Object.entries(rules)) {
    const block = element("details"); block.append(element("summary", name), element("pre", text)); $("rules").append(block);
  }
}
async function refreshOverview() {
  S.package = await api(`${base()}?reviewer=${encodeURIComponent(S.reviewer)}`); renderOverview();
}
function readFilters() {
  return {split: $("split").value, status: $("status").value,
    q: $("query").value, document_key: $("document").value, attribute: $("attribute").value,
    limit: $("pageSize").value};
}
function filterParams(offset = S.offset, anchor = "") {
  return new URLSearchParams({...S.filters, offset: String(offset), anchor});
}
async function loadPage(anchor = "") {
  S.page = await api(`${base()}/cases?${filterParams(S.offset, anchor)}`);
  S.offset = S.page.offset;
  if (!S.page.items.length && S.offset > 0) {
    S.offset = Math.max(0, Math.ceil(S.page.total / Number(S.filters?.limit || $("pageSize").value)) - 1) * Number(S.filters?.limit || $("pageSize").value);
    S.page = await api(`${base()}/cases?${filterParams()}`);
  }
  $("queueCount").textContent = `${S.page.total} / ${S.page.selected_total}`;
  $("pageNumber").textContent = S.page.total
    ? `${S.offset + 1}–${Math.min(S.offset + Number(S.filters?.limit || $("pageSize").value), S.page.total)}` : "Keine Treffer";
  fillSelect($("document"), S.page.documents.map(d => [d, d]), "Alle Dokumente", $("document").value);
  renderQueue(); updatePagination();
}
function renderQueue() {
  $("caseList").replaceChildren();
  S.page.items.forEach(row => {
    const button = element("button", null, "case-link"); button.type = "button";
    button.setAttribute("aria-current", String(row.example_id === S.current?.source.example_id));
    button.dataset.exampleId = row.example_id;
    button.append(element("strong", `${row.position + 1}. ${row.document_key} · ${row.reference}`),
      element("small", `${row.split} · ${row.confirmed_count}/${row.attribute_count} bestätigt${row.conflicts.length ? " · Widerspruch" : ""}`));
    button.addEventListener("click", () => run(async () => {if (leave()) await loadCase(row.example_id);}));
    $("caseList").append(button);
  });
}
function renderSegments(container, segments) {
  container.replaceChildren();
  const chosen = new Set(S.cards.map(c => c.selectedProposal()?.proposal_sha256).filter(Boolean));
  for (const part of segments) {
    const marks = $("showEvidence").checked ? part.marks.filter(m => chosen.has(m.proposal_sha256)) : [];
    if (!marks.length) {container.append(document.createTextNode(part.text)); continue;}
    const purposes = [...new Set(marks.map(m => m.purpose))];
    const mark = element("mark", part.text, purposes.length > 1 ? "mixed" : purposes[0]);
    const meanings = {support: "Stützende Evidenz", counterevidence: "Gegenindiz", context: "Kontext"};
    mark.title = marks.map(m => `${meanings[m.purpose]} · ${labels[m.attribute] || m.attribute}`).join("; ");
    mark.setAttribute("aria-label", `${mark.title}: ${part.text}`); container.append(mark);
  }
}
function renderSource() {
  const data = S.current, source = data.source;
  renderSegments($("sourceText"), data.source_rendering.text);
  $("sourceFacts").replaceChildren();
  const origins = {confirmed: "Bestätigte Struktur", deterministic: "Deterministisch",
    source_extraction: "Quellenextraktion", unattributed: "Nicht autorisiert", unavailable: "Nicht verfügbar", excluded: "Ausgeschlossen"};
  const absent = element("details");
  absent.append(element("summary", "Nicht verfügbare Strukturfelder"));
  const priorities = {ancestor_heading: 0, heading: 1, clause_type: 2, canonical_section: 3, annex_status: 4};
  const facts = source.structure.facts.map((fact, index) => ({fact, index}));
  facts.sort((a, b) => (priorities[a.fact.field] ?? 5) - (priorities[b.fact.field] ?? 5)
    || b.fact.distance - a.fact.distance || a.index - b.index);
  facts.forEach(({fact, index}) => {
    const block = element("div", null, "fact");
    const name = element("p", `${fact.field}${fact.distance ? ` · Abstand ${fact.distance}` : ""}`, "fact-name");
    name.append(element("span", origins[fact.origin] || fact.origin, "badge"));
    const content = element("div", null, "fact-value");
    const segments = data.source_rendering.facts[`fact:${index}`];
    if (segments) renderSegments(content, segments); else content.textContent = fact.value === null ? "Nicht verfügbar" : valueText(fact.value);
    block.append(name, content, element("small", `${fact.source_reference} · ${fact.source_path}${fact.authority ? ` · ${fact.authority}` : ""}${fact.generator ? ` · ${fact.generator}` : ""}`));
    if (fact.evidence.length) block.append(element("p", fact.evidence.join("\n"), "muted"));
    (fact.value === null ? absent : $("sourceFacts")).append(block);
  });
  if (absent.children.length > 1) $("sourceFacts").append(absent);
  if (!source.structure.facts.length) $("sourceFacts").append(element("p", "Kein weiterer Strukturkontext eingefroren.", "muted"));
  $("sourceIds").replaceChildren();
  for (const key of ["example_id", "document_key", "clause_id", "content_hash", "context_sha256", "source_sha256"]) {
    $("sourceIds").append(element("dt", key), element("dd", source[key]));
  }
  $("sourceIds").append(element("dt", "package_sha256"), element("dd", data.package_sha256),
    element("dt", "rules_sha256"), element("dd", data.rules_sha256),
    element("dt", "review_revision"), element("dd", data.revision));
}
function attributeCard(attribute) {
  const data = S.current;
  const proposals = data.proposals.filter(p => p.attribute === attribute).reverse();
  const current = data.human_reviews.find(d => d.attribute === attribute);
  const root = element("article", null, "panel attribute-card"); root.dataset.attribute = attribute;
  root.append(element("h4", labels[attribute] || attribute), element("span", attribute, "field-key"));
  if (current) root.append(element("div", `${statuses[current.status]} · ${predicateText(current.predicate)}\n${current.reviewer} · Revision ${current.revision}${current.comment ? `\n${current.comment}` : ""}`, "human-current"));
  const proposalBox = element("div", null, "proposal");
  const select = element("select"); select.setAttribute("aria-label", `Vorschlagsrevision: ${attribute}`);
  proposals.forEach(p => select.append(option(p.proposal_sha256, `Rev. ${p.revision} · ${p.producer_kind} · ${p.model || p.producer}`)));
  const card = {attribute, current, root, selectedProposal: () => proposals.find(p => p.proposal_sha256 === select.value)};
  const proposalBody = element("div");
  function refreshProposal() {
    proposalBody.replaceChildren(); const p = card.selectedProposal();
    if (!p) {proposalBody.append(element("p", "Kein sichtbarer Vorschlag. Eigenständig entscheiden oder offenlassen.")); return;}
    proposalBody.append(element("p", predicateText(p.predicate), "predicate"), element("p", p.rationale));
    const details = element("details");
    details.append(element("summary", "Provenienz & Evidenzzitate"), element("p", `${p.producer} · ${p.model || "kein Modell"} · ${dateText(p.created_at)}`), element("p", p.provenance), element("p", p.proposal_sha256));
    p.evidence.forEach(e => details.append(element("p", `${e.purpose} · ${e.target}: „${e.quote}“`)));
    if (!p.evidence.length) details.append(element("p", "Keine Einzelpassage markiert; die Begründung ist am vollständigen Text zu prüfen."));
    proposalBody.append(details);
  }
  if (proposals.length) proposalBox.append(labelled("Vorbereitung – keine menschliche Bestätigung", select));
  proposalBox.append(proposalBody); root.append(proposalBox); refreshProposal();
  const fields = element("div", null, "decision-fields");
  const status = element("select"); card.status = status;
  status.append(option("", "Unverändert lassen / noch nicht prüfen"), option("confirmed", "Ausgewählten Vorschlag bestätigen"),
    option("corrected", "Eigenen Wert festlegen und bestätigen"), option("deferred", "Zurückstellen – Entscheidung bleibt offen"),
    option("rejected", "Ausgewählten Vorschlag ablehnen – ohne Sollwert"));
  [...status.options].forEach(o => {if (!proposals.length && ["confirmed", "rejected"].includes(o.value)) o.disabled = true;});
  const editorBox = element("div"), comment = element("textarea"); comment.rows = 2; comment.maxLength = 20000;
  comment.placeholder = "Bei eigenem Wert oder Änderung einer früheren Entscheidung erforderlich.";
  card.hasNote = () => Boolean(comment.value.trim());
  let editor;
  card.showEditor = () => {
    editorBox.replaceChildren(); editor = null;
    if (status.value === "corrected") {
      editor = predicateEditor(data.schemas[attribute], current?.predicate || card.selectedProposal()?.predicate, updateDirty);
      editorBox.append(editor.root);
    } else if (status.value === "confirmed") {
      editorBox.append(element("p", `Bestätigt wird exakt: ${predicateText(card.selectedProposal()?.predicate)}`, "muted"));
    } else if (["deferred", "rejected"].includes(status.value)) {
      editorBox.append(element("p", "Diese Entscheidung erzeugt keinen Sollwert. Das Attribut bleibt offen.", "muted"));
    }
    updateDirty();
  };
  status.addEventListener("change", card.showEditor);
  select.addEventListener("change", () => {
    // Changing evidence/proposal does not silently retarget an already staged confirmation.
    status.value = ""; card.showEditor(); refreshProposal(); renderSource();
  });
  fields.append(labelled("Meine Entscheidung", status), editorBox, labelled("Begründung / Kommentar", comment));
  comment.addEventListener("input", updateDirty); root.append(fields);
  card.read = () => {
    const outcome = status.value; if (!outcome) return null;
    if ((outcome === "corrected" || current) && !comment.value.trim()) {
      throw new Error(`${labels[attribute] || attribute}: Bei eigenem Wert oder Änderung eines Reviews ist eine Begründung erforderlich.`);
    }
    const result = {example_id: data.source.example_id, attribute, status: outcome, comment: comment.value.trim()};
    if (["confirmed", "rejected"].includes(outcome)) {
      const proposal = card.selectedProposal();
      if (!proposal) throw new Error("Kein sichtbarer Vorschlag ausgewählt.");
      result.proposal_sha256 = proposal.proposal_sha256;
    } else if (outcome === "corrected") result.predicate = editor.read();
    return result;
  };
  return card;
}
function renderCase() {
  const data = S.current;
  S.cards = [];
  $("empty").hidden = true; $("caseContent").hidden = false;
  $("reference").textContent = `${data.source.document_key} · ${data.source.reference}`;
  $("casePosition").textContent = `Fall ${data.position + 1} von ${data.selected_total} · Reviewer: ${S.reviewer}`;
  $("splitBadge").textContent = data.case.split === "holdout" ? "Holdout" : "Development";
  $("priority").textContent = data.case.split === "holdout"
    ? "Unabhängig ausgewählter Holdout. Historische Kandidatenantworten und Rankingbegründungen bleiben verborgen."
    : `Reviewpriorität: ${data.priority.priority ?? "Paketreihenfolge"} · ${data.priority.rationale}`;
  $("conflicts").hidden = !data.progress.conflicts.length;
  $("conflicts").textContent = data.progress.conflicts.join("\n");
  $("attributes").replaceChildren();
  data.case.attributes.forEach(attribute => {const card = attributeCard(attribute); S.cards.push(card); $("attributes").append(card.root);});
  renderSource();
  $("blindPanel").hidden = data.case.split !== "holdout" || (!data.holdout.blind && !data.holdout.unrevealed_recommendation_count);
  $("assessment").value = ""; S.assessmentDirty = false;
  $("exposureHistory").replaceChildren();
  if (data.holdout.assessments.length) {
    const box = element("details", null, "panel");
    box.append(element("summary", "Protokollierte Ersteinschätzungen / Einblendungen"));
    data.holdout.assessments.forEach(e => box.append(element("p", `${dateText(e.revealed_at)} · ${e.reviewer}: ${e.assessment}`)));
    $("exposureHistory").append(box);
  }
  $("reviewHistory").replaceChildren();
  for (const review of [...data.review_history].reverse()) {
    const row = element("div", `Revision ${review.revision} · ${labels[review.attribute] || review.attribute}\n${statuses[review.status]} · ${predicateText(review.predicate)}\n${review.comment}`, "history-entry");
    row.append(element("small", `${review.reviewer} · ${dateText(review.reviewed_at)} · ${review.decision_sha256}`));
    $("reviewHistory").append(row);
  }
  if (!data.review_history.length) $("reviewHistory").append(element("p", "Noch keine menschlichen Entscheidungen.", "muted"));
  $("attested").checked = false; updateDirty(); renderQueue();
}
async function loadCase(exampleId) {
  S.current = await api(`${base()}/case?${new URLSearchParams({example_id: exampleId, reviewer: S.reviewer})}`);
  renderCase();
  // Only position/identity are persisted here, never an implicit annotation or approval.
  await api(`${base()}/bookmark`, {package_sha256: S.current.package_sha256,
    reviewer: S.reviewer, example_id: exampleId});
}
async function adjacent(step) {
  const rows = S.page.items, index = rows.findIndex(r => r.example_id === S.current?.source.example_id);
  if (index >= 0 && rows[index + step]) return {id: rows[index + step].example_id, offset: S.offset};
  const size = Number(S.filters?.limit || $("pageSize").value);
  const offset = step > 0 ? S.page.next_offset : S.offset - size;
  if (offset === null || offset < 0) return null;
  const page = await api(`${base()}/cases?${filterParams(offset)}`);
  const row = step > 0 ? page.items[0] : page.items.at(-1);
  return row ? {id: row.example_id, offset} : null;
}
async function navigate(step) {
  assertActiveIdentity();
  if (!S.current || !leave()) return;
  const target = await adjacent(step);
  if (!target) {notice("Keine weiteren Fälle in dieser gefilterten Richtung."); return;}
  S.offset = target.offset; await loadPage(); await loadCase(target.id);
  $("caseArea").focus();
}
async function save(goNext = false) {
  assertActiveIdentity();
  if (!S.current) return;
  if (!$("attested").checked) throw new Error("Bitte die persönliche fachliche Prüfung ausdrücklich bestätigen.");
  if (S.assessmentDirty && !window.confirm("Die Ersteinschätzung ist noch nicht protokolliert. Entscheidungen speichern und diese Notiz verwerfen?")) return;
  const decisions = S.cards.map(card => card.read()).filter(Boolean);
  if (!decisions.length) throw new Error("Es ist keine Entscheidung ausgewählt. Unberührte Vorschläge werden nicht bestätigt.");
  const target = goNext ? await adjacent(1) : null;
  const current = S.current.source.example_id;
  const receipt = await api(`${base()}/decisions`, {view_token: S.current.view_token, human_attested: true, decisions});
  // A lost/stale response is never retried automatically as a fresh approval.
  S.cards = []; S.assessmentDirty = false;
  await refreshOverview();
  if (target) S.offset = target.offset;
  await loadPage(target?.id || current); await loadCase(target?.id || current);
  notice(`${receipt.decisions_saved} Entscheidung(en) gespeichert. Revision ${receipt.revision}. Keine Suiten veröffentlicht.`);
}
async function openPackage() {
  if (!leave()) return;
  const reviewer = $("reviewer").value.trim(), handle = $("packageSelect").value;
  if (!reviewer || !handle) throw new Error("Reviewer-Kennung und Paket auswählen.");
  S.reviewer = reviewer; S.handle = handle; S.cards = []; S.current = null;
  S.assessmentDirty = false; S.offset = 0;
  $("caseContent").hidden = true; $("overview").hidden = true; $("workbench").hidden = true;
  try {localStorage.setItem("atlas-review-identity", reviewer); localStorage.setItem("atlas-review-handle", handle);} catch { /* optional convenience only */ }
  await refreshOverview();
  fillSelect($("attribute"), S.package.profile.attributes.map(a => [a, labels[a] || a]), "Alle Attribute");
  $("split").value = "all"; $("status").value = "all"; $("query").value = ""; $("document").value = "";
  S.filters = readFilters();
  $("overview").hidden = false; $("workbench").hidden = false;
  const resume = S.package.resume_example_id;
  if (resume) S.offset = Math.floor(S.package.queue_order.indexOf(resume) / Number(S.filters?.limit || $("pageSize").value)) * Number(S.filters?.limit || $("pageSize").value);
  await loadPage();
  if (resume || S.page.items.length) await loadCase(resume || S.page.items[0].example_id);
  notice(resume ? "Letzte gespeicherte Position wiederhergestellt." : "Paket geöffnet. Vorschläge sind keine bestätigten Sollentscheidungen.");
}
$("setup").addEventListener("submit", event => {event.preventDefault(); run(openPackage);});
$("filters").addEventListener("submit", event => {event.preventDefault(); run(async () => {
  if (!leave()) return; S.offset = 0; S.filters = readFilters(); await loadPage();
  if (S.page.items.length) await loadCase(S.page.items[0].example_id);
  else {S.current = null; S.cards = []; S.assessmentDirty = false; $("caseContent").hidden = true; $("empty").hidden = false; $("empty").textContent = "Keine Fälle für diese Filter. Die Paketmitgliedschaft bleibt unverändert.";}
});});
$("attribute").addEventListener("change", () => {if ($("attribute").value) $("status").value = "open";});
$("prevPage").addEventListener("click", () => run(async () => {
  if (!leave()) return; S.offset = Math.max(0, S.offset - Number(S.filters?.limit || $("pageSize").value));
  await loadPage(); if (S.page.items.length) await loadCase(S.page.items[0].example_id);
}));
$("nextPage").addEventListener("click", () => run(async () => {
  if (!leave() || S.page.next_offset === null) return; S.offset = S.page.next_offset;
  await loadPage(); if (S.page.items.length) await loadCase(S.page.items[0].example_id);
}));
$("prevCase").addEventListener("click", () => run(() => navigate(-1)));
$("nextCase").addEventListener("click", () => run(() => navigate(1)));
$("reloadCase").addEventListener("click", () => run(async () => {
  if (!leave()) return; await refreshOverview(); await loadPage(); await loadCase(S.current.source.example_id);
}));
$("showEvidence").addEventListener("change", () => {if (S.current) renderSource();});
$("assessment").addEventListener("input", () => {S.assessmentDirty = Boolean($("assessment").value);});
$("reveal").addEventListener("click", () => run(async () => {
  assertActiveIdentity();
  if (S.cards.some(c => c.status.value)) throw new Error("Zuerst die ausgewählten Entscheidungen speichern oder zurücksetzen. Einblenden lädt den Fall neu.");
  const assessment = $("assessment").value.trim();
  if (!assessment) throw new Error("Bitte zuerst eine eigene fachliche Ersteinschätzung notieren.");
  await api(`${base()}/reveal`, {view_token: S.current.view_token, assessment});
  S.assessmentDirty = false; await loadCase(S.current.source.example_id);
  notice("Ersteinschätzung und Einblendung protokolliert. Es wurde noch keine Sollentscheidung gespeichert.");
}));
$("selectSuggested").addEventListener("click", () => {
  S.cards.forEach(card => {
    if (!card.status.value && card.selectedProposal() && !["confirmed", "corrected"].includes(card.current?.status)) {
      card.status.value = "confirmed"; card.showEditor();
    }
  });
  updateDirty(); notice("Sichtbare Vorschläge vorgemerkt, nicht gespeichert. Jeden Vorschlag prüfen und anschließend ausdrücklich bestätigen.");
});
$("save").addEventListener("click", () => run(() => save(false)));
$("saveNext").addEventListener("click", () => run(() => save(true)));
window.addEventListener("beforeunload", event => {if (dirty()) {event.preventDefault(); event.returnValue = "";}});
window.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {event.preventDefault(); run(() => save(false));}
  if (event.altKey && ["ArrowLeft", "ArrowRight"].includes(event.key)) {event.preventDefault(); run(() => navigate(event.key === "ArrowRight" ? 1 : -1));}
});
await run(async () => {
  const bootstrap = await api("/api/bootstrap"); S.csrf = bootstrap.csrf_token;
  const packages = await api("/api/packages");
  fillSelect($("packageSelect"), packages.items.map(p => [p.handle, `${p.id} · ${p.cases} Fälle · ${p.handle}`]), "Paket auswählen …");
  try {$("reviewer").value = localStorage.getItem("atlas-review-identity") || "";
    $("packageSelect").value = localStorage.getItem("atlas-review-handle") || "";} catch { /* no persistent browser storage required */ }
  if (!$("packageSelect").value && packages.items.length === 1) $("packageSelect").value = packages.items[0].handle;
  if (packages.unavailable.length) notice(`${packages.unavailable.length} Paket(e) sind nicht lesbar oder ungültig. Details lokal prüfen.`);
  if (!packages.items.length) notice("Keine lesbaren Reviewpakete im konfigurierten Verzeichnis. Zuerst partial-review-build bzw. partial-review-apply-selection ausführen.");
});
