/* Data-only formatting; clause/model strings are never markup or executable code. */
export const labels = {
  applicability_present: "Applicability present",
};
export const statuses = {confirmed: "Confirmed", corrected: "Corrected / independently confirmed",
  deferred: "Deferred – open", rejected: "Proposal rejected – open"};
export function valueText(value) {
  if (value === null) return "No primary assignment (null)";
  if (value === true) return "Yes (true)";
  if (value === false) return "No (false)";
  if (Array.isArray(value)) return value.length ? value.map(valueText).join(" · ") : "No values (empty list)";
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}: ${valueText(v)}`).join("; ");
  return String(value);
}
export function predicateText(predicate) {
  if (!predicate) return "No expected decision yet";
  if (Object.hasOwn(predicate, "equals")) return `Exactly: ${valueText(predicate.equals)}`;
  if (Object.hasOwn(predicate, "must_include")) return `At least: ${valueText(predicate.must_include)}`;
  if (predicate.must_be_empty === true) return "Must be empty (explicit negative decision)";
  return "Invalid predicate operator";
}
export function dateText(value) {
  return new Intl.DateTimeFormat("en-GB", {dateStyle: "medium", timeStyle: "short"}).format(new Date(value));
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
