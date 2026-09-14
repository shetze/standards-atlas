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
| Engineering Document | persistence | `engineering-document` (9, current-only) | — | `.atlas/data/documents/*.json` |
| AtlasData enrichments | public contract | `atlasdata-enrichments` (`1.2`) | retained decision identities | `<AtlasData parent>/enrichments/<physical-key>.yaml` |
| Private knowledge evidence | persistence | `knowledge-evidence` (`1.0`) | content-addressed payload | `.atlas/data/knowledge-evidence/<sha256>.json` |
| AtlasData transfer report | persistence | `atlasdata-knowledge-report` (`1.0`) | — | `local/review/atlasdata-knowledge*.json` |
| Standards manifest | process | `standards-manifest` | — | `manifests/standards*.yaml` |
| Partial request plan (experimental) | persistence | `partial-request-plan` (1.1, current-only) | source/rule/task identities | `**/partial-request-plan.json` |
| Partial semantic observation (experimental) | persistence | `partial-semantic-observation` (1.1, current-only) | model/prompt/request identities | `**/partial-observation.json` |
| Partial experiment plan/report | persistence | `partial-proposal-run` (1.0) | frozen selection/configuration | `**/partial-run-*.json` |
| Qualification consensus | persistence | `qualification-consensus` (5.0, current-only) | model/prompt/stage identity | `**/consensus-report.json` |
| Golden corpus proposal | persistence | `golden-corpus-proposal` (4.0) | — | `**/golden-corpus-proposal.yaml` |
| Qualification Matrix manifest | process | `qualification-matrix-manifest` (1.6, current-only) | — | `manifests/*qualification*.yaml` |
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

The optional `atlasdata-enrichments` companion has an explicit `schema_version: "1.2"` and
`manifest_type: atlasdata-enrichments`. It is a versioned transport of selected canonical attributes,
not a second canonical model. It does not change the existing text grammar or canonical schema 9.
See [AtlasData format](atlas-data-format.md#accepted-enrichment-companions-schema-12).

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

## Remaining qualification contracts (refactoring R3)

| Schema family | Sole readable/writable version |
| --- | --- |
| `cascade-provenance` | 1.6 |
| `qualification-matrix-report` | 1.1 |
| `qualification-consensus` | 5.0 |
| `engineering-document` | 9 (integer marker) |
| `knowledge-adoption-batch` | 1.1 |
| `qualification-matrix-manifest` | 1.6 |

Markers are explicit. There is no v8 document upgrade, schema-4 consensus hash-preserving
serializer, or schema-1.0 adoption batch. Current adoption serialization always includes
`source_requirements`, including an explicit empty list. Repository inventories do not hide
obsolete documents. Named embedded evidence is validated before archive publication or use;
conflicting archive member aliases are rejected instead of choosing one silently.

Historical **current-contract** reports remain useful: raw missing vote keys remain
unobserved, explicit `false`/`null`/empty selections remain explicit, and measurements do not
become zero just because they are unavailable. Historical **obsolete-contract** inputs are
rejected, not migrated or treated as proof of an unexposed Holdout.

The review-only golden proposal remains its separate schema **4.0**. Archive layout/metadata
**1.5**, prompt/task/resource identities, timing semantics, and public enrichment companion
**1.2** are unchanged. All R1/R2 and Handoff families retain their contracts.
See [Remaining schema refactoring R3](../user-guide/remaining-schema-refactoring.md).


### Partial cascade readiness artifacts (Slice 5.1)

`partial-cascade-report` is a separate family from the immutable `partial-cascade-run`
plan. Current report version **1.1** explicitly binds run mode and effective configuration,
and makes a planning-only completion rate `null`. Since refactoring slice R1, **1.0**
reports are rejected, including on resume; no legacy metrics path remains. The independent
cascade-run and mixed-consensus contracts retain their existing versions. Verification
always recomputes the selected prompt/resources and presentation metrics instead of
trusting diagnostic counts as acceptance authority.

R1 also restricts `partial-request-plan` and `partial-semantic-observation` to **1.1**.
Each marker is mandatory and validated independently, including nested plans and direct
model reads. Prompt variants share the current serialization contract; a prompt's ability
to carry accepted decisions remains a separate capability. Writers check their own
family's current version before publication. No serializer preserves old 1.0 identities.
See [Partial schema refactoring R1](../user-guide/partial-schema-refactoring.md) for
regeneration and same-contract resume rules. Other schema families are unchanged by R1.

The diagnostic families `partial-cascade-audit`, `taxonomy-pilot-readiness`,
`taxonomy-readiness-cases`, `semantic-readiness-checks` and `semantic-readiness-evaluation`
start at **1.0**. Their rules and constraints are registered in the central schema baseline
and inventory. These reports/checks do not constitute semantic Golden data, a source
confirmation, a taxonomy-rule release or canonical publication authority.


## Human review and qualification handoff

The review package/state, Workbench state and semantic reference suites keep schema 1.0.
Review publication **1.1** is current-only and requires a replay-validated Workbench-evidence
envelope (1.0), with explicit journal presence, exact exposure/proposal bindings and every
recorded revision. Missing evidence is rejected; no legacy serializer preserves 1.0 identities.
An explicit `journal_present: false` means not recorded, not proof of no earlier exposure.

`partial-review-archive` and `partial-review-handoff` remain **1.0** with closed member
inventories. The frozen review package, review/preparation histories, Workbench history and
all package-bound inputs stay in the archive. A handoff binds that archive to the confirmed
Development/Holdout pair and its generated campaign manifest.

`partial-qualification-manifest` **1.1** is current-only with a required version marker.
`review_bundle` remains a manifest-relative pointer, mutually exclusive with
`semantic_suites`. Other input fields keep their existing project-relative semantics.
The supplied source manifest and standard test fixtures use 1.1; a Handoff does not
silently upgrade its input manifest.

Every `partial-qualification-campaign` artifact uses **2.0** with mandatory
`review_evidence.kind`:

| Kind | Required additional frozen inputs | Meaning |
| --- | --- | --- |
| `external_suites` | None | External suite provenance, no Atlas review-binding claim |
| `atlas_publication` | `inputs/semantic-review-bindings.json` | Complete Atlas publication pairs; external suites may coexist |
| `archived_handoff` | The binding file plus `inputs/review-package.zip` | Exactly one published review snapshot with its full archive |

The kind is derived from verified inputs during creation and explicitly checked on every
read. Exact manifest/physical inventories, suite references, source/context/rules bindings,
publication replay and archive replay must agree. There is no missing-file fallback, and
changing the kind cannot remove a Handoff's archive requirement. Evidence fields are part
of the campaign fingerprint, never part of model requests or an automatic release decision.

Obsolete manifests/publications 1.0 and campaign artifacts 1.0/1.1/1.2 are rejected, including
nested/direct reads. Writer guards run before output publication. Refactoring does not
rewrite existing archives, preserve superseded campaign hashes or alias old execution
results to new campaigns. See [Review schema refactoring R2](../user-guide/review-schema-refactoring.md).
