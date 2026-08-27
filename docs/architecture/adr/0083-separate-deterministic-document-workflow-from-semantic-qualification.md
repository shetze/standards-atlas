# ADR 0083: Separate deterministic document workflow from semantic qualification

## Status

Accepted.

## Context

The shared workflow planner historically placed LLM-assisted `classify-semantics` directly in
`--task documents`. This made canonical document generation depend on an available LLM runtime and
caused the deterministic document pipeline to inherit model lifecycle, response-validity, and
retry concerns. At the same time the qualification planner explicitly removed the ontology stage,
although semantic qualification is the use case that actually requires those classifications.

The refactored architecture now treats `EngineeringDocument` as the canonical deterministic
document representation and keeps model-derived semantic interpretation rebuildable and
qualifiable. Structural taxonomy remains deterministic and is required by both task families.

## Decision

Make semantic-profile classification an explicit planner capability instead of an unconditional
document stage.

`--task documents` executes only the deterministic document and publication pipeline:

- Docling extraction;
- AtlasData import/onboarding;
- normalization, reference detection, alignment, and review;
- content enrichment;
- deterministic structural taxonomy;
- multi-part family composition;
- Markdown export;
- Doorstop export and hierarchy publication when configured.

It does not schedule `document classify-semantics`, does not pass `--llm-config`, and does not
require an LLM runtime.

`--task qualification` opts into semantic-profile classification after taxonomy and before family
composition/corpus construction. The stage still classifies complete selected documents rather
than only the `--limit` sample, so persisted documents are never left with a qualification-specific
partial semantic profile. `--limit` continues to constrain only qualification execution stages.

`SEMANTIC_CLASSIFICATION` and `classify-semantics` name the multidimensional semantic-profile classifier explicitly. They do not refer to TBox/RBox/ABox/CBox construction.

## Consequences

- canonical document generation and Markdown/Doorstop publication are deterministic and LLM-free;
- a documents overwrite run no longer starts a model merely to build publishable documents;
- semantic-profile classification is owned by qualification orchestration, where model/runtime
  behavior is expected and observable;
- qualification still receives structural taxonomy context before semantic classification;
- family composition must tolerate documents without model-derived semantic classifications and
  merely preserve them when present;
- qualification plans continue to omit Doorstop export/publication while retaining Markdown
  reference publication;
- `--limit` cannot create partially semantic-classified EngineeringDocuments;
- ADRs 0067 and 0068 remain authoritative for taxonomy-versus-semantic ownership, but their
  placement of the semantic stage inside the documents workflow is superseded by this decision.
