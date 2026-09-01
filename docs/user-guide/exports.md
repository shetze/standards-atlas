# Exports

Exports consume persisted `EngineeringDocument` data. They do not extract PDFs or repair missing review decisions.

## Markdown

```bash
uv run standards-atlas document export markdown EN50716   --output local/markdown/EN50716
```

Use `--replace` to replace existing files. Multi-part families produce a navigable set of Markdown documents. Internal clause references are rendered as relative links when the referenced clause is available in the exported knowledge-domain set; unresolved or external references remain textual and traceable.

## Doorstop workspace

```bash
uv run standards-atlas document export doorstop EN50716   --hierarchy functional-safety
```

The export reads canonical EngineeringDocument data from `.atlas/data` and writes the rebuildable Doorstop project below `.atlas/work/doorstop`. Publication into consumable local output is a separate step:

```bash
uv run standards-atlas doorstop publish functional-safety   --local-root local
```

`doorstop publish` reads `.atlas/work/doorstop/<hierarchy-key>` by default. Doorstop projects are retained workflow scratch artifacts, not persistent Standards Atlas data. Use replacement options deliberately. Published output is derived; private source content and local review material must not leak into public artifacts.

## Export readiness

Before export, verify:

- the canonical document exists;
- required alignment and AtlasData reviews are complete;
- all parts have stable identities and a clause `0` root;
- the selected hierarchy relationships are valid;
- copyright-sensitive content is written only to approved local destinations.

## Gemara and ComplyTime

Standards Atlas can publish linked Gemara `GuidanceCatalog` and `ControlCatalog` projections,
create evaluator-independent ComplyTime governance bundles, prepare ComplyPack authoring
workspaces, and resolve Gemara `EvaluationLog` results back to source clauses. For standard
families and use-case-specific filtering, Governance Selection Profiles keep catalog identities
stable while Gemara Policies select the applicable view.

See the complete [Gemara and ComplyTime integration guide](gemara-complytime.md) for commands,
artifact flow, traceability, policy selection, ComplyPack validation, OCI packaging, and feedback.
