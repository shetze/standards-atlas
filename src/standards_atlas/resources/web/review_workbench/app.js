import {dateText, element, labelled, labels, option, predicateText, statuses, valueText} from "./format.js";
import {predicateEditor} from "./editors.js";

const $ = id => document.getElementById(id);
const S = {csrf: "", handle: "", reviewer: "", package: null, page: null, current: null,
  cards: [], offset: 0, busy: false, filters: null, assessmentDirty: false};
function base() {return `/api/packages/${encodeURIComponent(S.handle)}`;}
function dirty() {return S.assessmentDirty || S.cards.some(card => card.status.value !== "" || card.hasNote?.());}
function assertActiveIdentity() {
  if ($("reviewer").value.trim() !== S.reviewer || $("packageSelect").value !== S.handle) {
    throw new Error("Reviewer or package changed. Select “Open / resume package” first; the displayed review still belongs to the previous identity.");
  }
}
function leave() {return !dirty() || window.confirm("Discard unsaved decisions / initial assessment?");}
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
  try {data = await response.json();} catch {throw new Error(`HTTP ${response.status}: invalid server response.`);}
  if (!response.ok) {
    const details = (data.details || []).map(d => `${d.loc.join(".")}: ${d.msg}`).join("\n");
    const suffix = response.status === 409
      ? "\nThe review state changed. Your input remains visible; reload deliberately and review it again." : "";
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
  $("dirtyStatus").textContent = count ? `${count} selected decision(s), not saved yet.`
    : S.cards.some(c => c.hasNote?.()) ? "Unsaved note without a selected decision."
    : "No unsaved decisions.";
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
  if (S.package.task === "assertion_knowledge") {
    const report = S.package.report;
    $("coverage").replaceChildren(element("section", null, "panel coverage-card"));
    $("coverage").firstChild.append(element("h3", "Entity / assertion review"),
      element("strong", `${report.confirmed} / ${report.selected} cases confirmed`),
      element("p", `${report.pending} cases remain pending. Selection or model proposals do not publish golden content.`, "muted"));
    $("report").replaceChildren(element("p", "Publication is based exclusively on server-bound human decisions; the Workbench itself does not publish a suite."));
    $("rules").replaceChildren(element("p", `Ontologies: ${S.package.ontology_versions.join(", ")}`, "muted"));
    return;
  }
  const {report, profile, rules} = S.package;
  $("coverage").replaceChildren();
  for (const split of ["development", "holdout"]) {
    const data = report.splits[split];
    const card = element("section", null, "panel coverage-card");
    const totalAttrs = data.selected_cases * profile.attributes.length;
    const confirmed = Object.values(data.confirmed_attributes).reduce((a, b) => a + b, 0);
    const progress = element("progress"); progress.max = Math.max(data.selected_cases, 1);
    progress.value = data.complete_cases; progress.setAttribute("aria-label", `${split}: fully confirmed cases`);
    card.append(element("h3", split === "holdout" ? "Holdout · separate selection" : "Development · known set"),
      element("strong", `${data.complete_cases} / ${data.selected_cases} cases complete`), progress,
      element("p", `${confirmed} / ${totalAttrs} attributes confirmed. Open cases do not count as negative annotations.`, "muted"));
    $("coverage").append(card);
  }
  const reportBox = $("report"); reportBox.replaceChildren();
  reportBox.append(element("p", report.ready_for_publication
    ? "Semantic completeness check passed. Publication and validation against current sources still happen through the CLI import."
    : `${report.unresolved.length} open attributes · ${report.coverage_gaps.length} coverage gaps · ${report.conflicts.length} semantic conflicts.`));
  reportBox.append(element("p", "The view checks the frozen package; it does not claim unchanged live sources or independent prior use of the holdout.", "muted"));
  const details = element("details"); details.append(element("summary", "Full coverage report"),
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
    ? `${S.offset + 1}–${Math.min(S.offset + Number(S.filters?.limit || $("pageSize").value), S.page.total)}` : "No matches";
  fillSelect($("document"), S.page.documents.map(d => [d, d]), "All documents", $("document").value);
  renderQueue(); updatePagination();
}
function renderQueue() {
  $("caseList").replaceChildren();
  S.page.items.forEach(row => {
    const button = element("button", null, "case-link"); button.type = "button";
    button.setAttribute("aria-current", String(row.example_id === S.current?.source.example_id));
    button.dataset.exampleId = row.example_id;
    button.append(element("strong", `${row.position + 1}. ${row.document_key} · ${row.reference}`),
      element("small", `${row.split} · ${row.confirmed_count}/${row.attribute_count} confirmed${row.conflicts.length ? " · conflict" : ""}`));
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
    const meanings = {support: "Supporting evidence", counterevidence: "Counter-evidence", context: "Context"};
    mark.title = marks.map(m => `${meanings[m.purpose]} · ${labels[m.attribute] || m.attribute}`).join("; ");
    mark.setAttribute("aria-label", `${mark.title}: ${part.text}`); container.append(mark);
  }
}
function renderSource() {
  const data = S.current, source = data.source;
  renderSegments($("sourceText"), data.source_rendering.text);
  $("sourceFacts").replaceChildren();
  const origins = {confirmed: "Confirmed structure", deterministic: "Deterministic",
    source_extraction: "Source extraction", unattributed: "Unauthorized", unavailable: "Unavailable", excluded: "Excluded"};
  const absent = element("details");
  absent.append(element("summary", "Unavailablee Strukturfelder"));
  const priorities = {ancestor_heading: 0, heading: 1, clause_type: 2, canonical_section: 3, annex_status: 4};
  const facts = source.structure.facts.map((fact, index) => ({fact, index}));
  facts.sort((a, b) => (priorities[a.fact.field] ?? 5) - (priorities[b.fact.field] ?? 5)
    || b.fact.distance - a.fact.distance || a.index - b.index);
  facts.forEach(({fact, index}) => {
    const block = element("div", null, "fact");
    const name = element("p", `${fact.field}${fact.distance ? ` · distance ${fact.distance}` : ""}`, "fact-name");
    name.append(element("span", origins[fact.origin] || fact.origin, "badge"));
    const content = element("div", null, "fact-value");
    const segments = data.source_rendering.facts[`fact:${index}`];
    if (segments) renderSegments(content, segments); else content.textContent = fact.value === null ? "Unavailable" : valueText(fact.value);
    block.append(name, content, element("small", `${fact.source_reference} · ${fact.source_path}${fact.authority ? ` · ${fact.authority}` : ""}${fact.generator ? ` · ${fact.generator}` : ""}`));
    if (fact.evidence.length) block.append(element("p", fact.evidence.join("\n"), "muted"));
    (fact.value === null ? absent : $("sourceFacts")).append(block);
  });
  if (absent.children.length > 1) $("sourceFacts").append(absent);
  if (!source.structure.facts.length) $("sourceFacts").append(element("p", "No additional structural context is frozen.", "muted"));
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
  const select = element("select"); select.setAttribute("aria-label", `Proposal revision: ${attribute}`);
  proposals.forEach(p => select.append(option(p.proposal_sha256, `Rev. ${p.revision} · ${p.producer_kind} · ${p.model || p.producer}`)));
  const card = {attribute, current, root, selectedProposal: () => proposals.find(p => p.proposal_sha256 === select.value)};
  const proposalBody = element("div");
  function refreshProposal() {
    proposalBody.replaceChildren(); const p = card.selectedProposal();
    if (!p) {proposalBody.append(element("p", "No visible proposal. Decide independently or leave open.")); return;}
    proposalBody.append(element("p", predicateText(p.predicate), "predicate"), element("p", p.rationale));
    const details = element("details");
    details.append(element("summary", "Provenance & evidence quotes"), element("p", `${p.producer} · ${p.model || "no model"} · ${dateText(p.created_at)}`), element("p", p.provenance), element("p", p.proposal_sha256));
    p.evidence.forEach(e => details.append(element("p", `${e.purpose} · ${e.target}: “${e.quote}”`)));
    if (!p.evidence.length) details.append(element("p", "No individual passage is marked; review the rationale against the complete source."));
    proposalBody.append(details);
  }
  if (proposals.length) proposalBox.append(labelled("Preparation – not a human confirmation", select));
  proposalBox.append(proposalBody); root.append(proposalBox); refreshProposal();
  const fields = element("div", null, "decision-fields");
  const status = element("select"); card.status = status;
  status.append(option("", "Leave unchanged / not reviewed yet"), option("confirmed", "Confirm selected proposal"),
    option("corrected", "Set and confirm own value"), option("deferred", "Defer – decision remains open"),
    option("rejected", "Reject selected proposal – no expected value"));
  [...status.options].forEach(o => {if (!proposals.length && ["confirmed", "rejected"].includes(o.value)) o.disabled = true;});
  const editorBox = element("div"), comment = element("textarea"); comment.rows = 2; comment.maxLength = 20000;
  comment.placeholder = "Required for an own value or a change to a previous decision.";
  card.hasNote = () => Boolean(comment.value.trim());
  let editor;
  card.showEditor = () => {
    editorBox.replaceChildren(); editor = null;
    if (status.value === "corrected") {
      editor = predicateEditor(data.schemas[attribute], current?.predicate || card.selectedProposal()?.predicate, updateDirty);
      editorBox.append(editor.root);
    } else if (status.value === "confirmed") {
      editorBox.append(element("p", `Confirm exactly: ${predicateText(card.selectedProposal()?.predicate)}`, "muted"));
    } else if (["deferred", "rejected"].includes(status.value)) {
      editorBox.append(element("p", "This decision creates no expected value. The attribute remains open.", "muted"));
    }
    updateDirty();
  };
  status.addEventListener("change", card.showEditor);
  select.addEventListener("change", () => {
    // Changing evidence/proposal does not silently retarget an already staged confirmation.
    status.value = ""; card.showEditor(); refreshProposal(); renderSource();
  });
  fields.append(labelled("My decision", status), editorBox, labelled("Rationale / comment", comment));
  comment.addEventListener("input", updateDirty); root.append(fields);
  card.read = () => {
    const outcome = status.value; if (!outcome) return null;
    if ((outcome === "corrected" || current) && !comment.value.trim()) {
      throw new Error(`${labels[attribute] || attribute}: A rationale is required for an own value or a change to a review.`);
    }
    const result = {example_id: data.source.example_id, attribute, status: outcome, comment: comment.value.trim()};
    if (["confirmed", "rejected"].includes(outcome)) {
      const proposal = card.selectedProposal();
      if (!proposal) throw new Error("No visible proposal selected.");
      result.proposal_sha256 = proposal.proposal_sha256;
    } else if (outcome === "corrected") result.predicate = editor.read();
    return result;
  };
  return card;
}
function assertionSelect(options, value = "") {
  const select = element("select"); select.append(option("", "Select from ontology …"));
  options.forEach(item => select.append(option(item.iri, `${item.label} · ${item.iri}`))); select.value = value; return select;
}
function assertionEvidencePicker(data, changed) {
  const root = element("div", null, "panel"), picks = [];
  root.append(element("p", "Mark evidence: select text within a source surface and then add it.", "muted"));
  const list = element("div");
  data.source.surfaces.forEach(surface => {
    const block = element("div", null, "fact");
    const text = element("pre", surface.text); text.dataset.sourceRef = surface.source_ref;
    const add = element("button", "Add selected passage"); add.type = "button";
    add.addEventListener("click", () => {
      const selection = window.getSelection(); const quote = selection?.toString() || "";
      if (!quote || !text.contains(selection.anchorNode) || !text.contains(selection.focusNode)) {showError(new Error("Select text within this source surface.")); return;}
      picks.push({source_ref: surface.source_ref, quote});
      list.append(element("p", `${surface.label}: “${quote}”`, "muted")); changed(); selection.removeAllRanges();
    });
    block.append(element("strong", `${surface.label} · ${surface.source_clause_id} · ${surface.source_kind}`), text, add); root.append(block);
  });
  root.append(list); return {root, read: () => picks};
}
function assertionKnowledgeEditor(data, changed) {
  const root = element("div"), entityRows = [], assertionRows = [];
  const entitiesBox = element("div"), assertionsBox = element("div");
  function addEntity(value = {}) {
    const row = element("div", null, "relation-row"); const id = element("input"); id.value = value.id || "";
    const label = element("input"); label.value = value.normalized_label || "";
    const cls = assertionSelect(data.class_options, value.class_iri || "");
    const evidence = assertionEvidencePicker(data, changed); const entry = {row,id,label,cls,evidence}; entityRows.push(entry);
    const remove=element("button","Remove entity"); remove.type="button"; remove.addEventListener("click",()=>{row.remove();entityRows.splice(entityRows.indexOf(entry),1);changed();});
    row.append(labelled("Readable ID",id), labelled("Normalized label",label), labelled("Class",cls), evidence.root, remove); entitiesBox.append(row);
  }
  function addAssertion(value = {}) {
    const row=element("div",null,"relation-row"), id=element("input"); id.value=value.id||"";
    const subject=element("input"); subject.value=value.subject_id||""; const predicate=assertionSelect(data.predicate_options,value.predicate||"");
    const kind=element("select"); kind.append(option("entity","Entity endpoint"),option("literal","Literal")); kind.value=value.object?.kind||"entity";
    const object=element("input"); object.value=value.object?.entity_id||value.object?.value||"";
    const force=element("select"); ["unspecified","requirement","recommendation","permission","informative"].forEach(v=>force.append(option(v,v))); force.value=value.normative_force||"unspecified";
    const evidence=assertionEvidencePicker(data,changed); const entry={row,id,subject,predicate,kind,object,force,evidence}; assertionRows.push(entry);
    const remove=element("button","Remove assertion"); remove.type="button"; remove.addEventListener("click",()=>{row.remove();assertionRows.splice(assertionRows.indexOf(entry),1);changed();});
    row.append(labelled("Readable ID",id),labelled("Subject ID",subject),labelled("Predicate",predicate),labelled("Object kind",kind),labelled("Object / literal",object),labelled("Normative Force",force),evidence.root,remove); assertionsBox.append(row);
  }
  const addE=element("button","+ Entity"); addE.type="button"; addE.addEventListener("click",()=>{addEntity();changed();});
  const addA=element("button","+ Assertion"); addA.type="button"; addA.addEventListener("click",()=>{addAssertion();changed();});
  root.append(element("h4","Entities"),entitiesBox,addE,element("h4","Assertions"),assertionsBox,addA);
  return {root, seed(expected){(expected?.entities||[]).forEach(addEntity); (expected?.assertions||[]).forEach(addAssertion);}, read(){
    const entities=entityRows.map(e=>{if(!e.id.value.trim()||!e.label.value.trim()||!e.cls.value) throw new Error("Entity requires ID, label and ontology class."); return {id:e.id.value.trim(),class_iri:e.cls.value,normalized_label:e.label.value.trim(),evidence:e.evidence.read()};});
    const assertions=assertionRows.map(a=>{if(!a.id.value.trim()||!a.subject.value.trim()||!a.predicate.value||!a.object.value.trim()) throw new Error("Assertion requires ID, subject, predicate and object."); return {id:a.id.value.trim(),subject_id:a.subject.value.trim(),predicate:a.predicate.value,object:a.kind.value==="entity"?{kind:"entity",entity_id:a.object.value.trim()}:{kind:"literal",value:a.object.value.trim()},normative_force:a.force.value,evidence:a.evidence.read()};});
    return {entities,assertions};
  }};
}
function renderAssertionCase() {
  const data=S.current; S.cards=[]; $("empty").hidden=true; $("caseContent").hidden=false;
  $("reference").textContent=`${data.source.document_key} · ${data.source.reference}`; $("casePosition").textContent=`Case ${data.position+1} of ${data.selected_total} · reviewer: ${S.reviewer}`;
  $("splitBadge").textContent=data.case.split==="holdout"?"Holdout":"Development";
  $("splitBadge").classList.add("assertion-key-badge");
  $("priority").className="assertion-guidance";
  $("priority").textContent=data.case.split==="holdout"?"Holdout: review the source first; model proposals remain hidden by default.":"Review the source first. A model proposal is separate preparation and never a confirmation by itself.";
  $("conflicts").hidden=true; $("attributes").replaceChildren(); $("sourceText").replaceChildren(); $("sourceFacts").replaceChildren();
  const targetSurfaces=data.source.surfaces.filter(surface=>surface.source_clause_id===data.source.clause_id);
  const targetHeading=targetSurfaces.find(surface=>surface.source_kind==="heading");
  const targetBody=targetSurfaces.find(surface=>surface.source_kind==="body");
  const target=element("section",null,"assertion-target-source");
  target.append(
    element("p","Target clause · immediate review basis","assertion-target-kicker"),
    element("p","Target heading","assertion-target-field-label"),
    element("h3",targetHeading?.text||"No source heading","assertion-target-heading"),
    element("p","Target body","assertion-target-field-label assertion-target-body-label"),
    element("div",targetBody?.text||"No source body","assertion-target-body")
  );
  $("sourceText").append(target);
  data.source.surfaces.filter(surface=>surface.source_clause_id!==data.source.clause_id).forEach(surface=>{
    const block=element("div",null,"fact assertion-context-source");
    block.append(element("strong",`${surface.source_clause_id} · ${surface.source_kind}`),element("pre",surface.text));
    $("sourceFacts").append(block);
  });
  const root=element("section",null,"attribute-card"), status=element("select"); status.append(option("","Not decided yet"),option("confirmed","Confirm visible proposal"),option("corrected","Correct / provide own result"),option("deferred","Unclear / source missing"),option("rejected","Reject proposal"));
  if(!data.proposal){[...status.options].find(o=>o.value==="confirmed").disabled=true;}
  const comment=element("textarea"); comment.rows=2; const explicitEmpty=element("input"); explicitEmpty.type="checkbox";
  const editorBox=element("div"), proposalBox=element("details"); proposalBox.append(element("summary",data.proposal?"Show model proposal separately":"No model proposal available"),element("pre",data.proposal?JSON.stringify(data.proposal,null,2):""));
  const editor=assertionKnowledgeEditor(data,updateDirty); if(data.human_review?.expected) editor.seed(data.human_review.expected);
  function redraw(){editorBox.replaceChildren(); if(status.value==="corrected") editorBox.append(editor.root,labelled("Explicitly empty entity / assertion result",explicitEmpty)); else if(status.value==="confirmed") editorBox.append(element("p","Confirm exactly the visible, bound proposal.","muted")); updateDirty();}
  status.addEventListener("change",redraw); comment.addEventListener("input",updateDirty); root.append(proposalBox,labelled("My decision",status),editorBox,labelled("Kommentar",comment)); $("attributes").append(root); redraw();
  const card={status,hasNote:()=>Boolean(comment.value.trim()),selectedProposal:()=>data.proposal,showEditor:redraw,current:data.human_review,read:()=>{if(!status.value)return null; const out={status:status.value,comment:comment.value.trim(),explicit_empty:false}; if(status.value==="confirmed") out.proposal_sha256=data.proposal.proposal_sha256; if(status.value==="corrected"){const value=editor.read(); out.entities=value.entities; out.assertions=value.assertions; out.explicit_empty=explicitEmpty.checked; if(out.explicit_empty&&(out.entities.length||out.assertions.length))throw new Error("An explicitly empty result cannot also contain entities/assertions.");} return out;}}; S.cards=[card];
  $("blindPanel").hidden=true; $("assessment").value=""; S.assessmentDirty=false; $("exposureHistory").replaceChildren(); $("reviewHistory").replaceChildren();
  if(data.human_review) $("reviewHistory").append(element("pre",JSON.stringify(data.human_review,null,2))); else $("reviewHistory").append(element("p","No human decision yet.","muted"));
  $("attested").checked=false; updateDirty(); renderQueue();
}
function renderCase() {
  if (S.current?.task === "assertion_knowledge") {renderAssertionCase(); return;}
  const data = S.current;
  S.cards = [];
  $("empty").hidden = true; $("caseContent").hidden = false;
  $("reference").textContent = `${data.source.document_key} · ${data.source.reference}`;
  $("casePosition").textContent = `Case ${data.position + 1} of ${data.selected_total} · reviewer: ${S.reviewer}`;
  $("splitBadge").textContent = data.case.split === "holdout" ? "Holdout" : "Development";
  $("splitBadge").classList.remove("assertion-key-badge");
  $("priority").className = "muted";
  $("priority").textContent = data.case.split === "holdout"
    ? "Independently selected holdout. Historical candidate responses and ranking rationales remain hidden."
    : `Review priority: ${data.priority.priority ?? "package order"} · ${data.priority.rationale}`;
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
    box.append(element("summary", "Recorded initial assessments / reveals"));
    data.holdout.assessments.forEach(e => box.append(element("p", `${dateText(e.revealed_at)} · ${e.reviewer}: ${e.assessment}`)));
    $("exposureHistory").append(box);
  }
  $("reviewHistory").replaceChildren();
  for (const review of [...data.review_history].reverse()) {
    const row = element("div", `Revision ${review.revision} · ${labels[review.attribute] || review.attribute}\n${statuses[review.status]} · ${predicateText(review.predicate)}\n${review.comment}`, "history-entry");
    row.append(element("small", `${review.reviewer} · ${dateText(review.reviewed_at)} · ${review.decision_sha256}`));
    $("reviewHistory").append(row);
  }
  if (!data.review_history.length) $("reviewHistory").append(element("p", "No human decisions yet.", "muted"));
  $("attested").checked = false; updateDirty(); renderQueue();
}
async function loadCase(exampleId) {
  S.current = await api(`${base()}/case?${new URLSearchParams({example_id: exampleId, reviewer: S.reviewer})}`);
  renderCase();
  // Only position/identity are persisted here, never an implicit annotation or approval.
  if (S.current.task !== "assertion_knowledge") await api(`${base()}/bookmark`, {package_sha256: S.current.package_sha256,
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
  if (!target) {notice("No more cases in this filtered direction."); return;}
  S.offset = target.offset; await loadPage(); await loadCase(target.id);
  $("caseArea").focus();
}
async function save(goNext = false) {
  assertActiveIdentity();
  if (!S.current) return;
  if (!$("attested").checked) throw new Error("Explicitly attest your personal semantic review.");
  if (S.assessmentDirty && !window.confirm("The initial assessment has not been recorded yet. Save decisions and discard this note?")) return;
  const decisions = S.cards.map(card => card.read()).filter(Boolean);
  if (!decisions.length) throw new Error("No decision is selected. Untouched proposals are not confirmed.");
  const target = goNext ? await adjacent(1) : null;
  const current = S.current.source.example_id;
  const receipt = await api(`${base()}/decisions`, {view_token: S.current.view_token, human_attested: true, decisions});
  // A lost/stale response is never retried automatically as a fresh approval.
  S.cards = []; S.assessmentDirty = false;
  await refreshOverview();
  if (target) S.offset = target.offset;
  await loadPage(target?.id || current); await loadCase(target?.id || current);
  notice(`${receipt.decisions_saved} decision(s) saved. Revision ${receipt.revision}. No suites published.`);
}
async function openPackage() {
  if (!leave()) return;
  const reviewer = $("reviewer").value.trim(), handle = $("packageSelect").value;
  if (!reviewer || !handle) throw new Error("Select reviewer ID and package.");
  S.reviewer = reviewer; S.handle = handle; S.cards = []; S.current = null;
  S.assessmentDirty = false; S.offset = 0;
  $("caseContent").hidden = true; $("overview").hidden = true; $("workbench").hidden = true;
  try {localStorage.setItem("atlas-review-identity", reviewer); localStorage.setItem("atlas-review-handle", handle);} catch { /* optional convenience only */ }
  await refreshOverview();
  fillSelect($("attribute"), S.package.task === "assertion_knowledge" ? [] : S.package.profile.attributes.map(a => [a, labels[a] || a]), "All attributes");
  $("attribute").disabled = S.package.task === "assertion_knowledge";
  $("split").value = "all"; $("status").value = "all"; $("query").value = ""; $("document").value = "";
  S.filters = readFilters();
  $("overview").hidden = false; $("workbench").hidden = false;
  const resume = S.package.resume_example_id;
  if (resume) S.offset = Math.floor(S.package.queue_order.indexOf(resume) / Number(S.filters?.limit || $("pageSize").value)) * Number(S.filters?.limit || $("pageSize").value);
  await loadPage();
  if (resume || S.page.items.length) await loadCase(resume || S.page.items[0].example_id);
  notice(resume ? "Restored the last saved position." : "Package opened. Proposals are not confirmed expected decisions.");
}
$("setup").addEventListener("submit", event => {event.preventDefault(); run(openPackage);});
$("filters").addEventListener("submit", event => {event.preventDefault(); run(async () => {
  if (!leave()) return; S.offset = 0; S.filters = readFilters(); await loadPage();
  if (S.page.items.length) await loadCase(S.page.items[0].example_id);
  else {S.current = null; S.cards = []; S.assessmentDirty = false; $("caseContent").hidden = true; $("empty").hidden = false; $("empty").textContent = "No cases match these filters. Package membership remains unchanged.";}
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
  if (S.current?.task === "assertion_knowledge") throw new Error("Assertion review separates source and proposal directly; holdout proposals remain hidden.");
  if (S.cards.some(c => c.status.value)) throw new Error("Save or reset the selected decisions first. Revealing reloads the case.");
  const assessment = $("assessment").value.trim();
  if (!assessment) throw new Error("Record your own initial semantic assessment first.");
  await api(`${base()}/reveal`, {view_token: S.current.view_token, assessment});
  S.assessmentDirty = false; await loadCase(S.current.source.example_id);
  notice("Initial assessment and reveal recorded. No expected decision has been saved yet.");
}));
$("selectSuggested").addEventListener("click", () => {
  S.cards.forEach(card => {
    if (!card.status.value && card.selectedProposal() && !["confirmed", "corrected"].includes(card.current?.status)) {
      card.status.value = "confirmed"; card.showEditor();
    }
  });
  updateDirty(); notice("Visible proposals staged, not saved. Review each proposal and then confirm it explicitly.");
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
  fillSelect($("packageSelect"), packages.items.map(p => [p.handle, `${p.id} · ${p.cases} cases · ${p.handle}`]), "Select package …");
  try {$("reviewer").value = localStorage.getItem("atlas-review-identity") || "";
    $("packageSelect").value = localStorage.getItem("atlas-review-handle") || "";} catch { /* no persistent browser storage required */ }
  if (!$("packageSelect").value && packages.items.length === 1) $("packageSelect").value = packages.items[0].handle;
  if (packages.unavailable.length) notice(`${packages.unavailable.length} package(s) are unreadable or invalid. Check details locally.`);
  if (!packages.items.length) notice("No readable review packages in the configured directory. Run partial-review-build or partial-review-apply-selection first.");
});
