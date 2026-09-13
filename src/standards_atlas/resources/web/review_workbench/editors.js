/* Typed editors for the frozen review schema. No handwritten JSON/YAML is required. */
import {element, labelled, option, valueText} from "./format.js";

export function predicateEditor(schema, initial, changed) {
  const root = element("div", null, "value-editor");
  root.addEventListener("change", changed); root.addEventListener("input", changed);
  if (schema.type !== "array") {
    const input = element("select"); input.append(option("", "Wert ausdrücklich auswählen …"));
    const values = schema.type === "boolean" ? [true, false] : schema.enum || [];
    values.forEach((v, i) => input.append(option(String(i), valueText(v))));
    if (initial && Object.hasOwn(initial, "equals")) {
      const index = values.findIndex(v => v === initial.equals);
      if (index >= 0) input.value = String(index);
    }
    root.append(labelled("Bestätigter Wert", input));
    return {root, read: () => {
      if (!input.value) throw new Error("Bitte einen Wert auswählen; nicht geprüft ist kein Negativwert.");
      return {equals: values[Number(input.value)]};
    }};
  }
  const operator = element("select");
  operator.append(option("equals", "Genau diese Werte"), option("must_include", "Mindestens diese Werte"),
    option("must_be_empty", "Explizit: muss leer sein"));
  if (initial) operator.value = Object.keys(initial)[0];
  const body = element("div");
  root.append(labelled("Prüfoperator", operator), body);
  const values = initial?.equals || initial?.must_include || [];
  const emptyCheck = element("input"); emptyCheck.type = "checkbox";
  const emptyLabel = labelled("Die leere Liste ist meine ausdrückliche Entscheidung.", emptyCheck);
  emptyLabel.className = "inline";
  let readValues;
  if (schema.items?.type === "object") {
    const rows = element("div");
    const fields = Object.keys(schema.items.properties);
    const rowData = [];
    function add(value = {}) {
      const row = element("div", null, "relation-row");
      const inputs = {};
      fields.forEach(field => {
        const input = element("input"); input.value = value[field] || "";
        input.maxLength = 4000; inputs[field] = input;
        row.append(labelled(field, input));
      });
      const entry = {row, inputs}; rowData.push(entry);
      const remove = element("button", "Beziehung entfernen"); remove.type = "button";
      remove.addEventListener("click", () => {
        row.remove(); rowData.splice(rowData.indexOf(entry), 1); changed();
      });
      row.append(remove); rows.append(row);
    }
    values.forEach(add);
    const addButton = element("button", "+ Rollenbeziehung"); addButton.type = "button";
    addButton.addEventListener("click", () => { add(); changed(); });
    body.append(rows, addButton);
    readValues = () => rowData.map(entry => Object.fromEntries(fields.map(field => {
      const value = entry.inputs[field].value.trim();
      if (!value) throw new Error(`Rollenbeziehung: ${field} darf nicht leer sein.`);
      return [field, value];
    })));
  } else {
    const choices = element("div", null, "choices");
    const checkboxes = (schema.items?.enum || []).map(value => {
      const check = element("input"); check.type = "checkbox"; check.value = value;
      check.checked = values.includes(value);
      const label = labelled(value, check); label.className = "inline"; choices.append(label);
      return check;
    });
    body.append(choices);
    readValues = () => checkboxes.filter(c => c.checked).map(c => c.value);
  }
  body.append(emptyLabel);
  const visibility = () => {body.hidden = operator.value === "must_be_empty";};
  operator.addEventListener("change", visibility); visibility();
  return {root, read: () => {
    if (operator.value === "must_be_empty") return {must_be_empty: true};
    const selected = readValues();
    if (!selected.length && operator.value === "must_include") {
      throw new Error("‚Mindestens‘ benötigt einen Wert; eine leere Liste wäre kein wirksamer Prüfwert.");
    }
    if (!selected.length && !emptyCheck.checked) {
      throw new Error("Bitte Werte auswählen oder die leere Liste ausdrücklich bestätigen.");
    }
    return {[operator.value]: selected};
  }};
}
