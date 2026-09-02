const state = { prompts: [], models: [], contexts: [], clause: null };

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
  updateDescriptions();
}

function updateDescriptions() {
  const prompt = state.prompts.find((item) => `${item.task}/${item.version}` === controls.prompt.value);
  const model = state.models.find((item) => item.id === controls.model.value);
  const context = state.contexts.find((item) => item.id === controls.context.value);
  byId("promptDescription").textContent = prompt?.description || "Versionierter Prompt-Vertrag.";
  byId("modelDescription").textContent = model ? `${model.model_ref}${model.quantization ? ` · ${model.quantization}` : ""}` : "Kein RamaLama-Modell gefunden.";
  byId("contextDescription").textContent = context?.description || "CBox-Projektion für diesen Lauf.";
  byId("contextVariantBadge").textContent = context?.id || "—";
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
  controls.identifier.value = clause.id;
  controls.clause.value = clause.text;
  byId("clauseBadge").textContent = `${clause.document_key}:${clause.clause_reference} · ${clause.heading || "ohne Überschrift"}`;
  byId("clauseHash").textContent = clause.content_hash;
  await loadContext();
}

async function loadContext() {
  if (!state.clause) return;
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
controls.model.addEventListener("change", updateDescriptions);
byId("refreshButton").addEventListener("click", () => action(byId("refreshButton"), loadCatalogs));
byId("searchButton").addEventListener("click", () => action(byId("searchButton"), searchClauses));
byId("resolveButton").addEventListener("click", () => action(byId("resolveButton"), () => resolveClause()));
byId("activateButton").addEventListener("click", () => action(byId("activateButton"), activateModel));
byId("runButton").addEventListener("click", () => action(byId("runButton"), runExperiment));
controls.results.addEventListener("change", () => action(controls.results, () => resolveClause(controls.results.value)));
controls.identifier.addEventListener("keydown", (event) => { if (event.key === "Enter") action(byId("resolveButton"), () => resolveClause()); });
controls.query.addEventListener("keydown", (event) => { if (event.key === "Enter") action(byId("searchButton"), searchClauses); });

action(byId("refreshButton"), loadCatalogs);
checkRuntime();
