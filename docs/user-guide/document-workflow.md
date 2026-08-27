# Document workflow

The catalog-driven workflow is the preferred entry point. Individual commands remain useful for diagnosis and controlled development.

## Plan and run

```bash
uv run standards-atlas workflow plan   --manifests manifests/standards.yaml   --profile functional-safety

uv run standards-atlas workflow run   --manifests manifests/standards.yaml   --profile functional-safety
```

Select exactly one family selection mode. A hierarchy can be processed directly:

```bash
uv run standards-atlas workflow run   --manifests manifests/standards.yaml   --hierarchy functional-safety
```

Successful runs write JSON and Markdown derivation reports.

## Regeneration modes

- default: reuse valid persisted artefacts and stop on incomplete or incompatible state;
- `--overwrite`: regenerate derived artefacts;
- `--overwrite --keep docling`: regenerate later stages but retain extraction;
- `--force`: regenerate every reproducible stage, including Docling.

`--keep` is repeatable and valid only together with `--overwrite`.

## Run individual stages

### Extract

```bash
uv run standards-atlas docling convert SOURCE.pdf --document EN50716
uv run standards-atlas docling inspect EN50716
```

### Normalize

Normalization also preserves formula imagery when Docling identified a formula but could not transcribe it semantically. The existing conversion metadata is used to reopen the source PDF, and PyMuPDF renders only the recorded formula bounding boxes. No additional command is required.

```bash
uv run standards-atlas normalize run EN50716
uv run standards-atlas normalize inspect EN50716
```

### Detect references

```bash
uv run standards-atlas references detect EN50716
uv run standards-atlas references inspect EN50716
```

### Align and review

```bash
uv run standards-atlas align run EN50716 --atlasdata data/EN50716
uv run standards-atlas align inspect EN50716 --show-conflicts
```

Continue with [Alignment review](alignment-review.md) when the result is uncertain.

### Construct and classify structural taxonomy

The documents workflow imports the reviewed structure and enriches clauses from aligned normalized ranges. `ENRICH` only constructs content, evidence, reference mentions, and lineage; it does not perform structural or semantic classification. Persisted canonical documents are placed below `.atlas/data/documents/`.

The next stage is deterministic structural taxonomy:

```bash
uv run standards-atlas document classify-taxonomy EN50716
```

It materializes `StructuralProfile` and `StructuralContext`, including ancestor context, node/leaf role, sibling sequence position, contextual node content, and structural reference edges.

`--task documents` stops semantic processing at this deterministic boundary. It does not run `document classify-semantics`, does not require `cfg/llm.yaml`, and does not start a managed LLM endpoint. Family composition plus Markdown and configured Doorstop publication therefore operate on the canonical deterministic document representation.

`document classify-semantics` remains available as a diagnostic command, but normal workflow ownership moves to `--task qualification`, which runs the semantic-profile classifier after structural taxonomy. The historical command name refers to multidimensional semantic-profile classification and is distinct from the formal OWL TBox/RBox/ABox/CBox model.

Visual-only `FormulaBlock` entries retain their PNG asset and source evidence; formula transcription remains a separate enrichment concern.

## Review-aware continuation

After completing requested reviews, rerun the same selection with:

```bash
uv run standards-atlas workflow run   --manifests manifests/standards.yaml   --family EN50716   --continue-after-review
```

This flag does not approve proposals. It only permits execution when the expected reviewed artefacts already exist.
