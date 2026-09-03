# CLI reference

The authoritative option list is available through `--help` for every command.

```bash
uv run standards-atlas --help
uv run standards-atlas workflow run --help
```

## Top-level commands

- `info`: project information
- `validate`, `trace`: repository validation and traceability helpers
- `inspect data`: inspect legacy data artefacts
- `catalog validate`: validate catalog structure and references
- `workflow plan`, `workflow run`: plan or execute a typed-manifest workflow. The supported workflow tasks are `documents` and `qualification`; `documents` is the default. Qualification workflows accept `--limit` for a shared execution slice and `--fresh` to bypass proposal reuse and LLM response caches across matrix and semantic-extraction inference.


### Workflow manifest contract

`workflow plan` and `workflow run` accept workflow configuration through `--manifests`. The option may be repeated and each occurrence may also contain comma-separated paths. The workflow loader selects inputs by each file's `manifest_type`, not by filename or argument order.

```bash
uv run standards-atlas workflow plan \
  --task documents \
  --manifests manifests/standards.yaml \
  --all

uv run standards-atlas workflow plan \
  --task qualification \
  --manifests \
    manifests/standards.yaml,manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety
```

The unified `--manifests` interface belongs to the workflow envelope. Direct low-level commands remain intentionally specific: for example `evaluation qualification-matrix`, `evaluation challenger-qualification`, and `llm preload-qualification-models` use their own singular `--manifest` option because they consume one qualification-matrix manifest rather than a heterogeneous workflow manifest set.

## Local chat services

- `chat serve --service prompt-workbench`: run the local prompt experimentation UI.

The required `--service` option (alias `--service-type`) keeps the command family extensible;
there is no implicit service implementation. The prompt workbench binds to `127.0.0.1:8765`
by default and rejects non-loopback hosts.

## AtlasData

- `atlasdata onboard-docling`
- `atlasdata onboard-docling-parts`
- `atlasdata onboard-family`: manifest-driven multipart family onboarding
- `atlasdata set-status`
- `atlasdata generate-toc`

## Documents and exports

- `document import`
- `document derive`
- `document derive-part`
- `document enrich-content`
- `document classify-taxonomy`
- `document enrich-semantics`
- `document export markdown`
- `document export doorstop`
- `document export gemara`: Gemara GuidanceCatalog plus traceability sidecar
- `document export gemara-controls`: assessment-oriented Gemara ControlCatalog
- `document export complytime`: evaluator-independent governance source bundle
- `document export complypack`: ComplyPack authoring workspace and optional OCI packaging

## Extraction and normalization

- `docling convert`, `docling inspect`
- `normalize run`, `normalize inspect`

## Evaluation and qualification

- `evaluation corpus-build`: build a representative reusable clause corpus
- `evaluation qualification-matrix`: execute multidimensional semantic model qualification
- `evaluation applicability-detail-enrich`: enrich only final Applicability Presence-positive clauses with detailed functions and exact evidence
- `evaluation challenger-qualification`: compare configured challenger and incumbent models without changing the production cascade
- `evaluation normalization-quality`: run read-only linguistic-integrity qualification over an
  existing `dataset.json`; semantic labels are ignored

Example exploratory comparison using model definitions already present in the qualification
manifest:

```bash
uv run standards-atlas evaluation normalization-quality \
  --corpus .atlas/data/evaluation/corpora/semantic-profile/2.1.0/dataset.json \
  --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \
  --output local/evaluation/normalization-quality
```

By default the command selects the configured Mistral Small 3.2 24B and Gemma 3 12B candidates
when available. Repeat `--model MODEL_ID` to choose an explicit comparison set. `--limit` supports
small trial runs and `--no-cache` forces fresh inference. Outputs are `qualification.json`,
`findings.jsonl`, and `qualification.md`. The command never modifies an EngineeringDocument.

## Governance selection and Gemara policy authoring

- `governance profile validate PROFILE`: validate a Governance Selection Profile
- `governance profile show PROFILE`: render its normalized representation
- `governance profile select PROFILE`: classify Control candidates as `selected`, `excluded`, or
  `undetermined` with clause-local semantic evidence and emit JSON/CSV review artifacts
- `governance profile export-policy PROFILE`: create a draft Gemara Policy scaffold from Candidate
  Analysis v2, preserving Subject Group and matching-Clause provenance in its sidecar

Policy export requires explicit `--responsible` and `--accountable` contacts. Undetermined
candidates block export unless `--withhold-undetermined` is explicitly selected.

See [Gemara and ComplyTime integration](../user-guide/gemara-complytime.md).

## ComplyTime feedback

- `evaluation complytime-feedback --log LOG --bundle BUNDLE`: resolve a Gemara EvaluationLog to
  Standards Atlas clause, guideline, control, and assessment-requirement provenance.

## References and alignment

- `references detect`, `references inspect`
- `align run`, `align inspect`
- `align review`, `align review-export`
- `align review-validate`, `align review-diff`, `align review-import`
- `align validate-overrides`, `align review-apply`

Use the catalog-driven workflow for routine processing and individual commands for diagnostics or controlled partial execution.

## `clean`

```bash
uv run standards-atlas clean
uv run standards-atlas clean --cache
uv run standards-atlas clean --data --force
```

The default command removes only `.atlas/work`. `--cache` additionally removes
`.atlas/cache`. Persistent `.atlas/data` requires the explicit destructive
combination `--data --force`. Human-facing `local/` artifacts are never removed.
