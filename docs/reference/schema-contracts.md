# Schema contracts

Standards Atlas distinguishes **serialization schema versions** from **resource versions**. The executable inventory is defined in `standards_atlas.application.schema.inventory`; central reader/writer rules are defined by `SCHEMA_POLICIES`.

A serialization `schema_version` answers: **can this payload be deserialized safely?** A resource version answers: **which definition or behavior does this payload represent or reference?** Fields such as profile, ontology, taxonomy, task, prompt, model, and dataset versions therefore evolve independently from serialization schemas.

## Current compatibility phase

The project is currently in the explicit `REFACTORING` compatibility phase. Concrete policies may read only their current schema because obsolete intermediate refactoring contracts are intentionally unsupported. Writers always emit only the current schema.

The stable policy is already encoded as a bounded maximum reader window of three versions. Once the refactoring is declared complete and the project enters `STABLE`, each subsequent real schema revision retains up to the two immediately preceding real predecessor contracts:

| Relationship to current writer | Writer behavior | Stable reader behavior |
| --- | --- | --- |
| current (`N`) | emit | accept |
| previous (`N-1`) | never emit | accept with deprecation warning |
| oldest supported (`N-2`) | never emit | accept with deprecation warning |
| older | never emit | reject |

Removed refactoring schemas are not recreated merely to fill the stable support window.

## Lifecycle-crossing interface inventory

| Interface | Boundary | Schema axis | Resource axis | Location |
| --- | --- | --- | --- | --- |
| Engineering Document | persistence | `engineering-document` | — | `.atlas/data/documents/*.json` |
| Standards manifest | process | `standards-manifest` | — | `manifests/standards*.yaml` |
| Qualification Matrix manifest | process | `qualification-matrix-manifest` | — | `manifests/*qualification*.yaml` |
| Semantic task | packaged resource | `semantic-task-resource` | task version | `resources/semantic/tasks/<id>/<version>/task.yaml` |
| Semantic profile | packaged resource | `semantic-profile-resource` | profile version | `resources/semantic/profiles/<id>/<version>/profile.yaml` |
| Semantic ontology/vocabulary | packaged resource | `ontology-resource` | ontology version | `resources/ontologies/<id>/<version>/ontology.yaml` |
| Structural taxonomy | packaged resource | `structural-taxonomy-resource` | taxonomy version | `resources/structure-taxonomies/<id>/<version>/taxonomy.yaml` |
| Formal ontology | packaged resource | `formal-ontology-resource` | ontology version | `resources/formal_ontologies/<id>/<version>/ontology.yaml` |
| Semantic prompt | packaged resource | task-owned output schema | prompt version | `resources/semantic/prompts/<task>/<version>/` |
| Formal semantic projection | persistence | `formal-semantic-projection` | referenced ontology identities | `.atlas/data/formal-semantic-projections/*.json` |
| Semantic extraction | persistence | `semantic-extraction` | task/prompt/model provenance | `.atlas/data/semantic-extractions/*.json` |

`PublicationDocument` is intentionally absent. It is a runtime-only read model and has no independent persistence or compatibility lifecycle.

## Embedded version markers

Several persisted structures contain embedded/local markers such as normalization metadata, transformation ledgers, reference detection records, alignment records, workflow reports, and qualification archive records. A local marker is useful for auditability but does not automatically create a separate central schema family. It becomes one when that record acquires an independent reader/lifecycle boundary.

This avoids versioning every internal DTO while still making independently consumed contracts explicit.

## AtlasData

AtlasData is authored, Git-published, community-curated input and therefore has stronger preservation requirements than disposable derived artifacts. Its semantic profile reference is already explicitly resource-versioned. The AtlasData text grammar itself does not currently carry a standalone serialization `schema_version`; changes to that grammar must therefore remain backward-readable or be introduced with an explicit format-version mechanism before the project enters stable compatibility mode. AtlasData must not be treated as a disposable intermediate artifact.

## Packaged resource rule

For resources with both axes, directory/resource identity and `schema_version` have separate responsibilities. For example:

```text
resources/semantic/profiles/functional-safety/1.0.0/profile.yaml
                                      ^^^^^
                                      resource version

schema_version: 1
                ^
                serialization schema
```

A new profile such as `1.1.0` can still use schema `1`; conversely a future profile serialization schema `2` does not force the functional-safety profile itself to change meaning.

## Generated data

Standards Atlas does not promise in-place migration of generated artifacts. Compatibility is a reader concern: a supported old payload may deserialize into the current model, while writers emit only the current schema. Derived `.atlas/cache` and `.atlas/work` data are not compatibility contracts and may be invalidated freely.

See [ADR 0014](../architecture/adr/0014-schema-and-artifact-versioning-policy.md) for the normative policy.
