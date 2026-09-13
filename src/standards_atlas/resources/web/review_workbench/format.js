/* Data-only formatting; clause/model strings are never markup or executable code. */
export const labels = {
  primary_function: "Primäre Aussagefunktion", primary_knowledge_kind: "Primäre Wissensart",
  role_semantics_present: "Rollensemantik vorhanden", process_functions: "Prozessfunktionen",
  statement_functions: "Aussagefunktionen", knowledge_kinds: "Wissensarten",
  primary_process_function: "Primäre Prozessfunktion", applicability_present: "Applicability vorhanden",
  role_relations: "Rollenbeziehungen",
};
export const statuses = {confirmed: "Bestätigt", corrected: "Korrigiert / eigenständig bestätigt",
  deferred: "Zurückgestellt – offen", rejected: "Vorschlag abgelehnt – offen"};
export function valueText(value) {
  if (value === null) return "Keine primäre Zuordnung (null)";
  if (value === true) return "Ja (true)";
  if (value === false) return "Nein (false)";
  if (Array.isArray(value)) return value.length ? value.map(valueText).join(" · ") : "Keine Werte (leere Liste)";
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}: ${valueText(v)}`).join("; ");
  return String(value);
}
export function predicateText(predicate) {
  if (!predicate) return "Noch keine Sollentscheidung";
  if (Object.hasOwn(predicate, "equals")) return `Genau: ${valueText(predicate.equals)}`;
  if (Object.hasOwn(predicate, "must_include")) return `Mindestens: ${valueText(predicate.must_include)}`;
  if (predicate.must_be_empty === true) return "Muss leer sein (explizite Negativentscheidung)";
  return "Ungültiger Prüfoperator";
}
export function dateText(value) {
  return new Intl.DateTimeFormat("de-DE", {dateStyle: "medium", timeStyle: "short"}).format(new Date(value));
}
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
export function option(value, text) {
  const node = element("option", text); node.value = value; return node;
}
export function labelled(text, control) {
  const label = element("label", text); label.append(control); return label;
}
