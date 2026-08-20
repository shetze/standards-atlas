# Workspace

Standards Atlas separates generated artifacts by **audience** and **lifecycle**.
The location of an artifact therefore tells you whether it is persistent
machine state, disposable acceleration data, workflow scratch state, or a
human-facing result.

## Storage layout

```text
.atlas/
├── data/
│   ├── docling/
│   ├── normalized/
│   ├── reference-candidates/
│   ├── alignments/
│   ├── documents/
│   └── evaluation/
├── cache/
│   └── llm/
└── work/
    ├── workflow/
    ├── doorstop/
    └── llm/

local/
├── exports/
├── review/
│   ├── alignment/
│   ├── qualification/
│   └── normalization-quality/
└── evaluation/
```

### `.atlas/data`

Persistent machine-facing state. This includes native Docling artifacts,
normalized documents, detected references, automatic alignments, canonical
EngineeringDocuments, evaluation corpora, raw proposal runs, and machine
qualification state.

Deleting this directory can lose state or force expensive regeneration.

### `.atlas/cache`

Disposable caches. These artifacts may be removed at any time without changing
the semantic result of a complete rerun. The local LLM response cache is stored
under `.atlas/cache/llm`.

### `.atlas/work`

Temporary workflow scratch space. It is intentionally retained after a run so
that failed or surprising workflows can be debugged. A new `workflow run`
removes the previous work tree before it starts.

LLM process runtime state and workflow completion markers are examples of work
artifacts.

### `local`

Persistent human-facing output. Published Markdown and Doorstop content,
human-readable evaluation reports, archives, and editable review material live
here. Standards Atlas cleanup commands never remove this tree.

All HITL material is stored below `local/review`. Alignment reviews, semantic
qualification review queues, and normalization-quality review artifacts must
not be written to `.atlas` or another `local` subtree.

## Cleaning

Remove only retained workflow scratch data:

```bash
uv run standards-atlas clean
```

Remove scratch data and reproducible caches:

```bash
uv run standards-atlas clean --cache
```

Persistent machine state is protected. Removing it requires an explicit force:

```bash
uv run standards-atlas clean --data --force
```

None of these commands remove `local` artifacts.
