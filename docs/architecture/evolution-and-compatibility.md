# Evolution and compatibility

Standards Atlas evolves canonical domain objects, persisted artifacts, catalogs, command-line interfaces, and publication projections independently. This document defines the current compatibility policy and the decision criteria for migration, regeneration, deprecation, and deliberate breaking changes.

## Policy goals

The project favors explicit contracts and reproducible regeneration over indefinite compatibility layers. Compatibility is preserved where it protects authored input, reviewed decisions, or external integrations. Derived data may be invalidated and regenerated when the producing contract changes.

The policy distinguishes five surfaces:

| Surface | Default expectation | Primary authority |
|---|---|---|
| Canonical domain model | Breaking changes require an ADR and coordinated migration | Domain model and ADRs |
| Persisted internal artifacts | Versioned contracts; regenerate derived artifacts where possible | Artifact formats and persistence architecture |
| Catalog and authored configuration | Preserve or provide an explicit migration path | Catalog reference |
| CLI | Avoid accidental breakage; document intentional changes | CLI reference and changelog |
| Export formats | Stability depends on whether the format is canonical, compatibility-oriented, or derived | Format-specific reference and ADRs |

## Compatibility classes

### Authored and reviewed data

Human-authored catalogs, manual alignment overrides, accepted annotations, reviewed relationships, and other adjudicated decisions have the highest preservation priority. A change that cannot read these artifacts must provide one of:

1. an automated migration;
2. a documented, deterministic conversion;
3. an explicit decision that the old artifact is unsupported, including impact and recovery instructions.

Silent loss or reinterpretation is not acceptable.

### Canonical persisted data

Canonical `EngineeringDocument` artifacts and other versioned contracts must carry enough identity to determine whether a reader can interpret them safely. Readers must reject unsupported contract versions rather than guessing.

Migration is preferred when the artifact contains information that cannot be recreated from retained source and review evidence. Regeneration is preferred when the artifact is a deterministic derivative and all required inputs remain available.

### Derived artifacts

Docling output, normalized intermediate artifacts, derivation reports, generated Markdown, Doorstop projections, evaluation reports, embeddings, and retrieval indexes are derived unless a specific contract says otherwise. They may be invalidated when any of the following changes:

- producer version or algorithm identity;
- normalized-document or construction contract;
- source digest or catalog selection;
- taxonomy or classification schema;
- model, prompt, generation settings, or retrieval configuration;
- export policy or visibility rules.

Invalidation must be visible. The workflow must not quietly reuse an artifact whose recorded identity no longer matches the requested run.

## Regeneration versus migration

Use regeneration when all of these statements are true:

- the artifact is derived;
- authoritative inputs still exist;
- the transformation is reproducible enough for the intended use;
- no manual decision would be discarded.

Use migration when at least one of these statements is true:

- the artifact contains human-authored or reviewed information;
- source material is unavailable or cannot legally be retained in another form;
- regeneration would change stable external identifiers without a managed mapping;
- external systems depend on the existing artifact identity.

When neither approach is safe, stop and require explicit operator action.

## Domain-model changes

A domain-model change must identify:

- the affected entity, value object, invariant, and serializer;
- whether persisted artifacts remain readable;
- whether stable identifiers change;
- which application ports and adapters are affected;
- whether existing review data can still be attached unambiguously;
- which tests and documentation establish the new baseline.

Removed fields are not retained automatically as aliases. Compatibility properties or constructor shims require a specific use case, an owner, a removal condition, and test coverage. ADR 0008 is an example of an intentional removal without a compatibility layer.

## Catalog evolution

Catalogs are authored configuration and therefore receive a migration path when their schema changes materially. Additive optional fields are normally backward compatible. Renames, changed defaults, altered identity rules, and structural moves require:

- an updated [catalog reference](../reference/catalog-format.md);
- validation errors that name the obsolete construct;
- a conversion example or migration command where practical;
- a changelog entry.

Catalog readers must not reinterpret unknown fields silently.

## CLI evolution

Commands and options are user-facing interfaces. Intentional breaking changes must:

- be called out in the changelog;
- update the CLI reference, getting-started path, and affected user guides;
- provide a deprecation period when the old behavior is inexpensive and safe to retain;
- fail clearly when retaining both behaviors would be ambiguous or dangerous.

Exit codes are part of the operational contract and must be covered by integration tests.

## Export and projection evolution

Markdown and Doorstop outputs are projections, not the canonical domain model. Their layout may evolve, but stable links and identifiers should be preserved where consumers rely on them. A projection change must state whether it affects:

- filenames or relative links;
- clause anchors or external identifiers;
- visibility filtering;
- multipart composition;
- downstream import compatibility.

Legacy AtlasData compatibility is governed by its dedicated ADRs and reference documentation rather than by assuming all historical shapes remain supported.

## Deprecation lifecycle

A deprecation has four explicit stages:

1. **Announced** — replacement and rationale are documented.
2. **Warned** — validation or runtime output identifies use of the deprecated surface.
3. **Removed** — implementation and current documentation no longer expose it.
4. **Historical** — rationale remains in ADRs or `docs/history/` without appearing as a current contract.

A stage may be skipped when retaining the old behavior risks data corruption, security exposure, or architectural ambiguity. Such removal requires an ADR or equivalent explicit decision.

## Change checklist

A change affecting compatibility should answer:

- What is the canonical source of truth?
- Is the affected artifact authored, reviewed, canonical, or derived?
- Can it be regenerated without losing decisions?
- Which version or identity proves compatibility?
- How does an operator detect and recover from incompatibility?
- Which current documents, tests, and changelog entries change?

## Related documentation

- [Domain model](domain-model.md)
- [Persistence and lineage](persistence-and-lineage.md)
- [Workflow orchestration](workflow-orchestration.md)
- [Artifact formats](../reference/artifact-formats.md)
- [Catalog format](../reference/catalog-format.md)
- [ADR index](adr/README.md)
