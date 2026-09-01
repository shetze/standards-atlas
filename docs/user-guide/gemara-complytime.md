# Gemara and ComplyTime integration

Standards Atlas projects reviewed standards knowledge into Gemara governance artifacts and prepares
those artifacts for ComplyTime. The integration deliberately separates four concerns:

1. **Standards Atlas** owns standard structure, qualified semantics, stable clause identity, and provenance.
2. **Gemara catalogs** are generated interchange projections of that knowledge.
3. **Gemara policies** select a concrete use-case view from the larger governance space.
4. **ComplyPack and ComplyTime** attach evaluator-specific policy content, package it, execute assessments, and return evaluation results.

This matters for standard families: Standards Atlas does not create a different catalog for every
use case. Catalog identities remain stable; Governance Selection Profiles and Gemara Policies select
the applicable controls.

## Data flow

```text
EngineeringDocument / family publication
  -> GuidanceCatalog + ControlCatalog
  -> Governance Selection Profile
  -> Candidate Analysis (selected / excluded / undetermined)
  -> Gemara Policy scaffold
  -> evaluator-specific policy content
  -> ComplyPack workspace / optional OCI
  -> ComplyTime
  -> Gemara EvaluationLog
  -> Standards Atlas feedback
```

Generated Gemara, ComplyTime, and ComplyPack artifacts never replace the canonical
`EngineeringDocument`.

## Gemara contract and adapters

The adapter contract targets Gemara **1.1.0**. The version is centralized so GuidanceCatalog,
ControlCatalog, policy scaffolds, and hand-off artifacts use one contract. Gemara-specific models
and mappings live under `adapters/gemara`; the Standards Atlas domain remains Gemara-independent.

### GuidanceCatalog

```bash
uv run standards-atlas document export gemara EN50716
```

Default output:

```text
local/exports/gemara/EN50716.yaml
local/exports/gemara/EN50716.yaml.traceability.json
```

Structural nodes become groups. Qualified semantics determine whether content becomes guideline
objectives, statements, recommendations, rationale, or applicability context. Scope clauses provide
framing rather than duplicated guidance. Export is deterministic and performs no LLM call.

The sidecar maps Standards Atlas clause IDs to Gemara entry IDs and preserves relations that cannot
be represented losslessly in the catalog. Its SHA-256 binds it to the exact YAML export.

Multipart publications use the normal runtime composition options:

```bash
uv run standards-atlas document export gemara IEC61508   --part IEC61508-1 --part IEC61508-2 --part IEC61508-3   --title "IEC 61508"
```

### ControlCatalog

```bash
uv run standards-atlas document export gemara-controls EN50716
```

Default output:

```text
local/exports/gemara/EN50716-controls.yaml
local/exports/gemara/EN50716-controls.yaml.traceability.json
```

A source clause is not automatically a Control. Objective anchors become Controls only when
supported by normative assessment requirements; standalone normative requirements can be retained
as single-requirement Controls. Informative content and recommendations are not silently promoted
to mandatory requirements.

Controls link to their Layer-1 Guidance entries. Traceability preserves:

```text
source clause -> guideline / statement -> control -> assessment requirement
```

## ComplyTime governance bundle

```bash
uv run standards-atlas document export complytime EN50716
```

Default output:

```text
local/exports/complytime/EN50716/
  guidance.yaml
  controls.yaml
  traceability.json
  manifest.yaml
  lineage.json
```

The manifest records catalog identities, source version, Gemara version, paths, media types, and
hashes. Traceability consolidates the Guidance and Control mappings required by feedback import.
This command deliberately does **not** create `complypack.yaml`: a governance bundle is
evaluator-independent, while a ComplyPack is not.

## Selecting a use case

Keep catalogs stable and describe a concrete engineering context with a Governance Selection
Profile.

### Profile

```bash
uv run standards-atlas governance profile validate local/governance/rail-onboard-sil2.yaml
uv run standards-atlas governance profile show local/governance/rail-onboard-sil2.yaml
```

Example:

```yaml
schema-version: 1
id: rail-onboard-sil2
version: 1.0.0
context:
  domain: railway
  system-types: [onboard-software, linux]
  lifecycle-phases: [software-development, software-validation]
  integrity-levels: [SIL-2]
  roles: [software-developer, verifier]
  attributes:
    automation-level: GoA4
standards:
  include: [EN50716]
  exclude: []
selection:
  statement-functions: [requirement, conformance_statement]
applicability:
  require-present: true
  polarity: included
```

Engineering vocabulary remains open; existing canonical Standards Atlas semantic dimensions are
typed.

### Candidate analysis

```bash
uv run standards-atlas governance profile select   local/governance/rail-onboard-sil2.yaml   --document EN50716
```

Default output:

```text
local/review/governance/rail-onboard-sil2/
  candidate-analysis.json
  candidate-analysis.csv
```

Each Control is `selected`, `excluded`, or `undetermined`. Missing qualified evidence is never
guessed into a positive result. Decision precedence is:

```text
excluded > undetermined > selected
```

The CSV is the intended HITL review surface.

### Gemara Policy scaffold

```bash
uv run standards-atlas governance profile export-policy   local/governance/rail-onboard-sil2.yaml   --responsible "Rail Safety Engineering"   --accountable "Project Safety Manager"
```

Default output:

```text
local/exports/governance/rail-onboard-sil2/
  policy.yaml
  policy.yaml.scaffold.json
```

Scope, imports, and exclusions are deterministic. RACI contacts are explicit because organizational
responsibility cannot be derived from a technical standard. Evaluation methods, assessment plans,
frequency, evidence requirements, and executor selection are deliberately left for policy
authoring.

`undetermined` blocks export by default. To produce a draft while preserving the review boundary:

```bash
uv run standards-atlas governance profile export-policy   local/governance/rail-onboard-sil2.yaml   --responsible "Rail Safety Engineering"   --accountable "Project Safety Manager"   --withhold-undetermined
```

Withheld controls are excluded from effective imports and recorded in the scaffold sidecar.

## ComplyPack authoring

A ComplyPack combines governance provenance with **existing evaluator-specific policy content**.
Standards Atlas does not generate OPA/Rego, CEL, or other evaluator logic from normative prose.

```bash
uv run standards-atlas document export complypack EN50716   --policy-content ./local/policy   --gemara-source file:///absolute/path/to/policy.yaml   --evaluator-id opa   --pack-id org.example.en50716   --pack-version 0.1.0
```

Default workspace:

```text
local/exports/complypack/EN50716/
  governance/
  policy/
  complypack.yaml
  workspace-manifest.yaml
  lineage.json
```

`--gemara-source` identifies an existing Gemara **Policy**, not merely a GuidanceCatalog or
ControlCatalog. Supported schemes are `file`, `http`, `https`, and `oci`. Policy content must be
non-empty and may not contain symlinks.

### `--validate`

Adding `--validate` runs the external equivalent of:

```bash
complypack config validate complypack.yaml --unknown-fields=error --scope pack
```

It validates the generated **ComplyPack configuration**. It does not prove evaluator-policy
semantics or source resolvability. The installed ComplyPack must expose `config validate`; verify
with `complypack --help`.

### OCI packaging

Registry publication is opt-in via `--oci-target`:

```bash
uv run standards-atlas document export complypack EN50716   --policy-content ./local/policy   --gemara-source oci://registry.example/policies/en50716:v1   --evaluator-id opa   --pack-id org.example.en50716   --pack-version 0.1.0   --oci-target registry.example/packs/en50716:v0.1.0
```

Without `--oci-target` there is no registry write. A real pack requires the Gemara Policy source to
be resolvable; placeholder URIs are only useful for configuration smoke tests.

## EvaluationLog feedback

```bash
uv run standards-atlas evaluation complytime-feedback   --log local/evaluation/evaluation-log.yaml   --bundle local/exports/complytime/EN50716
```

Default output:

```text
local/evaluation/complytime/evaluation-log-feedback.json
```

The importer resolves Controls and Assessment Requirements through bundle traceability back to
source clauses and Guidance entries. It records aggregate outcomes such as `Passed`, `Failed`,
`Needs Review`, `Not Applicable`, `Unknown`, and `Not Run`.

Import is fail-closed for unknown IDs, mismatched Control/Assessment relationships, incompatible
Gemara versions, or modified traceability. Feedback remains a derived artifact and never mutates
the canonical EngineeringDocument.

## Recommended workflows

Complete standard:

```text
document export complytime
  -> author Gemara/evaluator policy
  -> document export complypack
  -> ComplyPack / OCI
  -> ComplyTime
  -> evaluation complytime-feedback
```

Use-case selection:

```text
governance profile validate
  -> governance profile select
  -> HITL review
  -> governance profile export-policy
  -> author evaluator-specific adherence/policy content
  -> document export complypack
  -> ComplyTime
  -> evaluation complytime-feedback
```

## Boundaries

- Gemara artifacts are rebuildable projections; change canonical inputs and regenerate.
- Do not treat `undetermined` as `selected`.
- Keep use-case selection in Gemara Policy rather than proliferating filtered catalog variants.
- Evaluator policy is executable logic and remains an explicit authoring concern.
- `--validate` validates ComplyPack configuration, not compliance correctness.
- OCI publication is never implicit.
- EvaluationLog feedback is evidence/reporting, not an automatic rewrite of standards knowledge.
