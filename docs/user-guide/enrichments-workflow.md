# End-to-end publication of AtlasData enrichments

`workflow run --task enrichments` connects the existing document preparation, qualification,
canonical adoption and AtlasData transfer services. It starts **after Docling extraction** and
ends with `data/enrichments/<physical-document-key>.yaml`, private evidence, a verified reimport
and a CBox report. It does not render Markdown or publish Doorstop.

The task is an explicit authorization to adopt and publish generated results. Merely running
`documents` or `qualification` still does not publish companions. Planning never writes files or
starts inference. The workflow uses the public planner/executor APIs and registered command
handlers in-process; there is no CLI-subprocess script or alternate normalization implementation.

## Prerequisites

Run from the project root. The standards manifest must own reviewed AtlasData structures for all
selected families. Their physical documents need native Docling JSON in
`.atlas/data/docling/<key>/document.json`. The real Docling adapter reads these artifacts; missing
or invalid extraction input stops the workflow, without synthetic text or an alternate parser.
Conversion metadata and source PDFs remain relevant for source-backed formula imagery.

The qualification matrix must enable final consensus and the Applicability decision policy. The
existing verified adoption reader requires their final artifacts; it does not accept arbitrary
proposal directories or substitute a Presence gate for the final policy. The snapshot's v6
Applicability Presence manifest meets this contract. Context routing uses
`cfg/context-enrichment.yaml` (currently `context-routing-v2`), and qualification uses the selected
matrix and existing LLM configuration. The configured models/runtime must be available to execute
new inference. Unknown or insufficient semantic outcomes retain their existing policy semantics;
this workflow does not change thresholds or turn generated values into confirmations.

## Plan and execute

```bash
uv run standards-atlas workflow plan \
  --task enrichments \
  --manifests manifests/standards.yaml,manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety
```

Execute the same selection:

```bash
uv run standards-atlas workflow run \
  --task enrichments \
  --manifests manifests/standards.yaml,manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety
```

Use `--family IEC61508`, repeated `--family` options, `--profile` or `--all` instead of the hierarchy
selector to choose another scope. Physical parts/supplements come from manifest bindings; a
synthetic family source is not qualified or published as an additional document. A family without
a reviewed AtlasData binding is rejected before execution rather than silently skipped.

The resulting sequence is:

```text
existing Docling JSON + reviewed AtlasData
  -> import/derive physical structure
  -> normalize using Docling adapter
  -> detect references -> align -> alignment review gate
  -> enrich content -> structural taxonomy (all selected documents)
  -> subject/context-routing enrichment (all selected documents)
  -> selected eligible corpus -> qualification cascade
  -> final Applicability policy (+ optional extraction qualification)
  -> immutable archive + checksum-verified handoff receipt
  -> canonical adoption
  -> export public companions + private evidence
  -> reimport -> canonical CBox report
```

All selected document structures are prepared before contextual enrichment so the subject
vocabulary sees the complete selected inventory. Failed routing inference stops the task before
qualification/publication, using `document enrich-context --fail-on-failure`. Standalone context
enrichment keeps its existing default diagnostic behavior unless that option is supplied.

## Full population versus samples

By default this task selects **all eligible clauses of the selected physical documents**, not the
500-clause qualification benchmark and not unrelated documents in the workspace. Existing
eligibility rules still exclude empty, table-dominant and Scope/Reference-meta clauses from the
semantic corpus. Context enrichment remains document-wide, including routing metadata. A missing
semantic result for an excluded clause is not an implicit negative. Corpus statistics, coverage,
adoption and CBox reports make these distinctions inspectable.

For a bounded trial, append `--corpus-count 50 --limit 50`. `--corpus-count` samples eligible
clauses; `--limit` bounds qualification, not document preparation/context inference. Partial runs
only adopt the selected qualified clauses and still publish the other existing canonical
attributes. They must not be interpreted as complete semantic coverage.

Standalone `--task qualification` retains its default corpus size of 500. The new low-level
`evaluation corpus-build --all-clauses` is mutually exclusive with `--count`, and `--document` is a
repeatable physical-document filter. The publication task additionally uses
`--source-only-context`: structural/subject/routing context remains input, but accepted semantic
predictions and their provenance are excluded from the corpus. Otherwise each adoption would
change the next corpus merely by writing the workflow's own semantic outputs back to its inputs.

## Review, reuse and regeneration

An unresolved alignment blocks downstream evaluation **and the global adoption/publication tail**.
Complete the existing alignment review procedure, then repeat the command with
`--continue-after-review`. This option is not review approval: content construction still needs a
valid reviewed alignment. A command failure is not recorded as a completed workflow stage.

Default execution reuses current persisted artifacts/checkpoints. Transfer preflight and the CBox
report run again against the actual current files. Archive reuse additionally requires unchanged
run inputs and a receipt whose exact ZIP bytes still match its SHA-256. A missing or altered ZIP is
not silently replaced with the most recently numbered archive.

- `--overwrite` rebuilds derived stages from persisted Docling artifacts. Use it after changing
  extraction/normalization inputs when a downstream artifact must be reconstructed.
- `--regenerate-docling` explicitly includes PDF conversion and downstream regeneration.
- `--fresh` refreshes qualification inference without response/proposal reuse; it does not
  implicitly overwrite Docling or all document artifacts.
- `--fresh-applicability-policy` refreshes that policy while reusing Presence qualification.
- `--restore-enrichments` restores available companions after taxonomy, before context enrichment.
  Add `--strict-evidence` to require private evidence during restoration/reimport.

`--force`, `--adopt-run` and `--publish-enrichments` are not used for this task. It publishes by
explicit task selection and adopts its own completed archive. To adopt an already existing archive
without document processing or new inference, continue using the separate `knowledge` task.

## Artifacts and archive handoff

The selection fingerprint includes document keys, matrix identity, corpus size/limit, strategy,
seed and knowledge domain. It isolates publication corpora/runs from standalone qualification and
other full/sample selections:

```text
.atlas/data/normalized/<key>/...
.atlas/data/documents/<key>.json
.atlas/data/evaluation/corpora/enrichments/<selection>/...
.atlas/data/evaluation/qualification/enrichments/<selection>/<matrix>/...
.atlas/data/knowledge-evidence/...
data/enrichments/<key>.yaml
local/evaluation/qualification-run-XXX.zip
local/review/enrichments-workflow/<selection>/
  archive.json
  adopt.json
  export.json
  reimport.json
  cbox.json
```

The planner prints these paths. `--corpus-output` and `--qualification-output` change the base
locations, with the task/selection suffix retained. Normal workflow JSON/Markdown derivation
reports are also written under `.atlas/work/workflow/runs/`.

`evaluation qualification-archive --receipt <path>` writes the receipt only after final archive
creation succeeds. It records the absolute archive path, ZIP SHA-256 and matrix identity.
`document adopt-qualification --run-receipt <path>` verifies that handoff and then uses the existing
member-verified archive reader. Exactly one of `--run` or `--run-receipt` is allowed; the workflow
never guesses an archive sequence number or selects a global `latest` ZIP. Receipts are local
handoff artifacts, not portable archive references; after moving a checkout, use a verified
archive's explicit `--run` path or regenerate the handoff.

Public publication policy stays unchanged: natural clause order, exact TOC MD5 references,
internal headings, grouped fingerprints, no public `ambiguous_candidates`, and role semantics as
presence only. Existing compatible companions are merged, not deleted. The task leaves the
reviewed structural AtlasData files and authoritative confirmations intact. Canonical schema 9,
companion schema 1.2 and private-evidence schema 1.0 do not change.

## Verification boundary

The integration regression uses two synthetic native Docling documents and executes real reading,
normalization, reference detection, alignment, content/taxonomy/context services, corpus building,
adoption, public/private transfer and checkpoint reuse. External model/policy/archive production
is represented by controlled qualification fixtures; these tests do not claim a production-model
quality assessment. A second identical run verifies byte-identical canonical documents and public
companions. Separate tests cover archive checksum/matrix validation, failed context inference,
review gates, selection isolation and CLI failure propagation without subprocess orchestration.
