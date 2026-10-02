const SOURCE_BOUND_TASK = "formal-semantic-knowledge-proposal";
const state = { prompts: [], models: [], contexts: [], clause: null, sourcePreview: null };

const byId = (id) => document.getElementById(id);
const controls = {
  prompt: byId("promptSelect"), context: byId("contextSelect"), model: byId("modelSelect"),
  identifier: byId("clauseIdentifier"), query: byId("clauseQuery"), results: byId("clauseResults"),
  system: byId("systemEditor"), user: byId("userEditor"), schema: byId("schemaEditor"),
  clause: byId("clauseEditor"), contextEditor: byId("contextEditor"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

function selectedPrompt() {
  return state.prompts.find((item) => `${item.task}/${item.version}` === controls.prompt.value);
}

function isSourceBoundKnowledge() {
  return selectedPrompt()?.task === SOURCE_BOUND_TASK;
}

async function loadCatalogs() {
  setBusy(byId("refreshButton"), true);
  try {
    const [prompts, models, contexts] = await Promise.all([
      api("/api/prompts"), api("/api/models"), api("/api/context-variants"),
    ]);
    state.prompts = prompts.items; state.models = models.items; state.contexts = contexts.items;
    controls.prompt.replaceChildren(...state.prompts.map((item) => option(`${item.task}/${item.version}`, `${item.task} · ${item.version}`)));
    controls.model.replaceChildren(...state.models.map((item) => option(item.id, item.id)));
    controls.context.replaceChildren(...state.contexts.map((item) => option(item.id, item.id)));
    const recommended = state.contexts.find((item) => item.id === "full-context-v1");
    if (recommended) controls.context.value = recommended.id;
    if (state.prompts.length) await loadPrompt();
    updateDescriptions();
  } finally { setBusy(byId("refreshButton"), false); }
}

async function loadPrompt() {
  const [task, version] = controls.prompt.value.split("/");
  if (!task || !version) return;
  const prompt = await api(`/api/prompts/${encodeURIComponent(task)}/${encodeURIComponent(version)}`);
  controls.system.value = prompt.system_prompt;
  controls.user.value = prompt.user_template;
  controls.schema.value = JSON.stringify(prompt.output_schema, null, 2);
  state.sourcePreview = null;
  updateDescriptions();
  if (state.clause) await loadContext();
}

function updateDescriptions() {
  const prompt = selectedPrompt();
  const model = state.models.find((item) => item.id === controls.model.value);
  const context = state.contexts.find((item) => item.id === controls.context.value);
  const sourceBound = isSourceBoundKnowledge();
  const policy = prompt?.policy_id ? ` · Policy ${prompt.policy_id}@${prompt.policy_version}` : "";
  const examples = prompt?.example_set_id ? ` · Beispiele ${prompt.example_set_id} (${prompt.example_set_partition})` : "";
  const qualification = prompt?.qualification_status ? ` · Status ${prompt.qualification_status}` : "";
  byId("promptDescription").textContent = (prompt?.description || "Versionierter Prompt-Vertrag.") + qualification + policy + examples;
  byId("modelDescription").textContent = model ? `${model.model_ref}${model.quantization ? ` · ${model.quantization}` : ""}` : "Kein RamaLama-Modell gefunden.";
  if (sourceBound) {
    controls.context.disabled = true;
    byId("contextDescription").textContent = "AP03: Quellenpaket und Kontextauswahl werden durch den produktiven source-bound Vertrag bestimmt.";
    byId("contextVariantBadge").textContent = "assertion-context-selection-v1";
    byId("previewButton").hidden = false;
    byId("runNote").textContent = "AP03-Lauf: versioniertes Bundle → produktiver source-bound Request → Gateway → Schema → produktiver Parser/Ontologie/Grounding. Schema-Erfolg ist kein semantischer Qualitätsnachweis.";
    controls.system.readOnly = true;
    controls.user.readOnly = true;
    controls.schema.readOnly = true;
  } else {
    controls.context.disabled = false;
    byId("contextDescription").textContent = context?.description || "CBox-Projektion für diesen Lauf.";
    byId("contextVariantBadge").textContent = context?.id || "—";
    byId("previewButton").hidden = true;
    byId("runNote").textContent = "Prompt, Klausel und ausgewählte Kontextprojektion werden strukturiert an RamaLama gesendet.";
    controls.system.readOnly = false;
    controls.user.readOnly = false;
    controls.schema.readOnly = false;
  }
  if (model) {
    byId("reasoning").checked = model.generation.reasoning_enabled;
    byId("maxTokens").placeholder = model.generation.max_output_tokens || "Modellstandard";
  }
}

async function searchClauses() {
  const query = controls.query.value.trim();
  const payload = await api(`/api/clauses?q=${encodeURIComponent(query)}&limit=30`);
  controls.results.replaceChildren(...payload.items.map((item) => option(item.id, `${item.document_key}:${item.clause_reference} — ${item.heading || item.text_preview}`)));
  controls.results.hidden = false;
  if (!payload.items.length) showToast("Keine passenden Klauseln gefunden.");
}

async function resolveClause(identifier = controls.identifier.value.trim()) {
  if (!identifier) throw new Error("Bitte eine Klausel-ID oder Referenz eingeben.");
  const clause = await api(`/api/clauses/resolve?identifier=${encodeURIComponent(identifier)}`);
  state.clause = clause;
  state.sourcePreview = null;
  controls.identifier.value = clause.id;
  controls.clause.value = clause.text;
  byId("clauseBadge").textContent = `${clause.document_key}:${clause.clause_reference} · ${clause.heading || "keine eigene Überschrift"}`;
  byId("clauseHash").textContent = clause.content_hash;
  await loadContext();
}

function ontologyVersions() {
  return byId("ontologyVersions").value.split(",").map((item) => item.trim()).filter(Boolean);
}

function sourceBoundRequest() {
  if (!state.clause) throw new Error("Bitte zuerst eine Klausel auswählen.");
  const prompt = selectedPrompt();
  const maxTokens = byId("maxTokens").value;
  const seed = byId("seed").value;
  return {
    clause_identifier: state.clause.id,
    prompt_version: prompt.version,
    model_id: controls.model.value || null,
    ontology_versions: ontologyVersions(),
    temperature: Number(byId("temperature").value),
    seed: seed === "" ? null : Number(seed),
    max_tokens: maxTokens === "" ? null : Number(maxTokens),
    reasoning_enabled: byId("reasoning").checked,
    use_cache: byId("useCache").checked,
  };
}

async function previewSourceBound() {
  if (!isSourceBoundKnowledge()) return;
  const payload = await api("/api/source-bound-knowledge/preview", { method: "POST", body: JSON.stringify(sourceBoundRequest()) });
  state.sourcePreview = payload;
  controls.contextEditor.value = JSON.stringify(payload.source_package, null, 2);
  controls.system.value = payload.request.system_prompt;
  controls.user.value = payload.request.user_prompt;
  controls.schema.value = JSON.stringify(payload.request.output_schema, null, 2);
  byId("compiledOutput").textContent = JSON.stringify({ request: payload.request, source_package: payload.source_package, interpretation_context: payload.interpretation_context, stages: payload.stages }, null, 2);
  byId("resultMeta").replaceChildren(...["Preview · kein Modellaufruf", payload.request.prompt_version].map((label) => {
    const badge = document.createElement("span"); badge.textContent = label; return badge;
  }));
}

async function loadContext() {
  if (!state.clause) return;
  if (isSourceBoundKnowledge()) {
    await previewSourceBound();
    return;
  }
  const payload = await api(`/api/context-preview?identifier=${encodeURIComponent(state.clause.id)}&variant=${encodeURIComponent(controls.context.value)}`);
  controls.contextEditor.value = payload.context_text;
  byId("contextVariantBadge").textContent = payload.variant.id;
}

async function activateModel() {
  const payload = await api("/api/models/activate", { method: "POST", body: JSON.stringify({ model_id: controls.model.value }) });
  showToast(`${payload.model.id} ist im RamaLama-Server aktiv.`);
  await checkRuntime();
}

async function runExperiment() {
  if (!state.clause) throw new Error("Bitte zuerst eine Klausel auswählen.");
  if (isSourceBoundKnowledge()) {
    const payload = await api("/api/source-bound-knowledge/run", { method: "POST", body: JSON.stringify(sourceBoundRequest()) });
    byId("resultOutput").textContent = JSON.stringify({ output: payload.output, proposal: payload.proposal, validation: payload.validation }, null, 2);
    byId("compiledOutput").textContent = JSON.stringify({ request: payload.request, source_package: payload.source_package, interpretation_context: payload.interpretation_context, generation: payload.generation, stages: payload.stages }, null, 2);
    const validation = payload.validation;
    const schema = validation.schema_valid ? "Schema gültig" : `${validation.schema_errors.length} Schemafehler`;
    const ontology = validation.ontology_valid === true ? "Ontologie gültig" : validation.ontology_valid === false ? "Ontologie fehlerhaft" : "Ontologie nicht geprüft";
    const grounding = validation.grounding_valid === true ? "Grounding gültig" : validation.grounding_valid === false ? "Grounding fehlerhaft" : "Grounding nicht geprüft";
    const badges = [schema, ontology, grounding, validation.technical_candidate_valid ? "Technisch akzeptiert" : "Technisch nicht akzeptiert", payload.generation.model];
    byId("resultMeta").replaceChildren(...badges.map((label, index) => {
      const badge = document.createElement("span"); badge.textContent = label;
      if ((index === 0 && !validation.schema_valid) || (index === 1 && validation.ontology_valid === false) || (index === 2 && validation.grounding_valid === false) || (index === 3 && !validation.technical_candidate_valid)) badge.className = "invalid";
      return badge;
    }));
    return;
  }

  let schema;
  try { schema = JSON.parse(controls.schema.value); }
  catch (error) { throw new Error(`Das Output-Schema ist kein gültiges JSON: ${error.message}`); }
  const [promptTask, promptVersion] = controls.prompt.value.split("/");
  const maxTokens = byId("maxTokens").value;
  const seed = byId("seed").value;
  const request = {
    clause_identifier: state.clause.id,
    prompt_task: promptTask,
    prompt_version: promptVersion,
    model_id: controls.model.value,
    context_variant: controls.context.value,
    system_prompt: controls.system.value,
    user_template: controls.user.value,
    output_schema: schema,
    temperature: Number(byId("temperature").value),
    seed: seed === "" ? null : Number(seed),
    max_tokens: maxTokens === "" ? null : Number(maxTokens),
    reasoning_enabled: byId("reasoning").checked,
    use_cache: byId("useCache").checked,
  };
  const payload = await api("/api/experiments", { method: "POST", body: JSON.stringify(request) });
  byId("resultOutput").textContent = JSON.stringify(payload.output, null, 2);
  byId("compiledOutput").textContent = JSON.stringify({ compiled_prompt: payload.compiled_prompt, request: payload.request, generation: payload.generation }, null, 2);
  const validity = payload.validation.valid ? "Schema gültig" : `${payload.validation.errors.length} Schemafehler`;
  const badges = [validity, `${payload.generation.duration_ms} ms`, payload.generation.model];
  if (payload.generation.cached) badges.push("Cache");
  byId("resultMeta").replaceChildren(...badges.map((label, index) => {
    const badge = document.createElement("span");
    badge.textContent = label;
    if (index === 0 && !payload.validation.valid) badge.className = "invalid";
    return badge;
  }));
}

async function checkRuntime() {
  const pill = byId("runtimePill");
  try {
    const runtime = await api("/api/runtime");
    pill.dataset.state = runtime.available ? "ready" : "error";
    byId("runtimeText").textContent = runtime.available ? `RamaLama bereit · ${runtime.models.join(", ") || "Modell aktiv"}` : "RamaLama nicht bereit";
  } catch (error) {
    pill.dataset.state = "error"; byId("runtimeText").textContent = "Runtime-Status nicht verfügbar";
  }
}

function setBusy(button, busy) { button.disabled = busy; button.setAttribute("aria-busy", String(busy)); }
function showToast(message) {
  const toast = byId("toast"); toast.textContent = message; toast.hidden = false;
  window.clearTimeout(showToast.timer); showToast.timer = window.setTimeout(() => { toast.hidden = true; }, 4500);
}
async function action(button, operation) {
  setBusy(button, true);
  try { await operation(); }
  catch (error) { showToast(error.message); }
  finally { setBusy(button, false); }
}

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
  document.querySelectorAll(".tab-pane").forEach((pane) => { pane.hidden = pane.dataset.pane !== tab.dataset.tab; });
}));
controls.prompt.addEventListener("change", () => action(controls.prompt, loadPrompt));
controls.context.addEventListener("change", () => action(controls.context, async () => { updateDescriptions(); await loadContext(); }));
controls.model.addEventListener("change", () => action(controls.model, async () => { updateDescriptions(); if (isSourceBoundKnowledge() && state.clause) await previewSourceBound(); }));
byId("refreshButton").addEventListener("click", () => action(byId("refreshButton"), loadCatalogs));
byId("searchButton").addEventListener("click", () => action(byId("searchButton"), searchClauses));
byId("resolveButton").addEventListener("click", () => action(byId("resolveButton"), () => resolveClause()));
byId("activateButton").addEventListener("click", () => action(byId("activateButton"), activateModel));
byId("previewButton").addEventListener("click", () => action(byId("previewButton"), previewSourceBound));
byId("runButton").addEventListener("click", () => action(byId("runButton"), runExperiment));
controls.results.addEventListener("change", () => action(controls.results, () => resolveClause(controls.results.value)));
controls.identifier.addEventListener("keydown", (event) => { if (event.key === "Enter") action(byId("resolveButton"), () => resolveClause()); });
controls.query.addEventListener("keydown", (event) => { if (event.key === "Enter") action(byId("searchButton"), searchClauses); });

for (const id of ["temperature", "seed", "maxTokens", "reasoning", "useCache", "ontologyVersions"]) {
  byId(id).addEventListener("change", () => {
    if (isSourceBoundKnowledge() && state.clause) action(byId("previewButton"), previewSourceBound);
  });
}

action(byId("refreshButton"), loadCatalogs);
checkRuntime();
