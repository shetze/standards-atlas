# Schema contracts

Standards Atlas distinguishes **serialization schema versions** from versions of the
content carried by those schemas. `schema_version` identifies a JSON/YAML contract.
Fields such as `version`, `task_version`, `taxonomy_version`, `prompt_version`, and
`dataset_version` identify domain content and evolve independently.

## Bounded compatibility policy

Version 0.8.2 establishes a clean baseline and a bounded reader policy. Each schema
family has one current version and may read at most the two immediately preceding
versions. A major Standards Atlas transition may temporarily permit a fourth readable
version. Writers emit only the current version. Supported non-current versions emit a
visible deprecation warning; older versions fail explicitly.

Because ADR 0063 deliberately removed historical compatibility, the current concrete
policies initially contain only their current version. Older versions are added only
when a future schema revision creates a real predecessor contract.

| Schema family / artifact | Current | Storage / resource | Future reader compatibility |
| --- | ---: | --- | --- |
| Engineering Document envelope | 3 | `.atlas/data/documents/*.json` | yes |
| Normalization metadata | 10 | `.atlas/data/normalized/**/document.json` | yes |
| Normalization transformation ledger | 1 | normalized document | yes |
| Normalization run metadata | 1 | `.atlas/data/normalized/**/run.json` | yes |
| Reference detection metadata | 2 | `.atlas/data/**` | yes |
| Alignment metadata | 2 | `.atlas/data/**` | yes |
| Alignment override / review metadata | 1 | `local/review/**` | yes, when re-imported |
| Engineering construction validation | 1 | `.atlas/data/**` | yes |
| Formula transcription | 1 | `.atlas/data/**` / review pipeline | yes |
| Standards manifest | 2 | `manifests/*.yaml` | yes |
| Qualification Matrix manifest | 1.5 | `manifests/*.yaml` | yes |
| Evaluation corpus manifest | 1.0 | `.atlas/data/evaluation/**` | yes |
| Semantic annotation | 1.0 | `.atlas/data/evaluation/**` | yes |
| Semantic consensus report | 2.1 | `.atlas/data/evaluation/**` | yes |
| Semantic review decision | 1.0 | `local/review/**` | yes |
| Qualification report | 1.0 | evaluation artifacts | yes |
| Qualification matrix report | 1.0 | evaluation artifacts | yes |
| Analysis archive | 1.1 | `local/evaluation/**` | only if machine-read later |
| Qualification run metadata | 1.1 | `local/evaluation/**` | only if machine-read later |
| Qualification run index | 1.0 | `local/evaluation/**` | only if machine-read later |
| Workflow run report | 3 | workflow audit output | yes |
| Semantic task resource | 1 | `resources/semantic/tasks/**/task.yaml` | yes |
| Ontology resource | 1 | `resources/ontologies/**/ontology.yaml` | yes |
| Structural taxonomy resource | 1 | `resources/structure-taxonomies/**/taxonomy.yaml` | yes |

The table is the compatibility inventory. Schema families that cross active reader
boundaries are routed through the central policy as those readers are maintained.
The policy window is an upper bound, not a requirement to retain obsolete versions.

## Storage classes

Durable machine state under `.atlas/data`, versioned packaged resources, workflow
manifests, and machine-consumed review contracts are compatibility-relevant.

`.atlas/cache` and `.atlas/work` are **not** compatibility contracts. They can be
invalidated or deleted whenever implementation or schema details change. Human-only
publications under `local/` also carry no machine-reader guarantee unless Standards
Atlas explicitly imports them again (for example HITL review decisions).

## Generated data

Standards Atlas does not promise in-place migration of generated artifacts. Future
compatibility is a reader concern: a supported old payload may deserialize directly
into the current Python/domain model. Writers emit only the current schema.

## Baseline and policy enforcement

The Engineering Document repository now rejects unversioned and pre-v3 payloads.
Standards and Qualification Matrix manifests are checked against their current
baselines at the workflow envelope. Semantic task, ontology, and structural
taxonomy YAML resources now carry an explicit `schema_version: 1`, validated by their
models/loaders. Persisted Pydantic contracts with existing fixed schema versions use
literal schema fields so arbitrary versions no longer validate accidentally.
