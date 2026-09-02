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

Governance Selection Profiles use schema version 2. Applicability is deliberately not a profile
selector. A profile selects governance content by independent semantic dimensions and engineering
context; normative applicability remains part of the underlying standard/Gemara semantics.

```bash
uv run standards-atlas governance profile validate local/governance/rail-onboard-sil2.yaml
uv run standards-atlas governance profile show local/governance/rail-onboard-sil2.yaml
```

Example:

```yaml
schema-version: 2
id: rail-onboard-sil2
version: 1.0.0
context:
  domain: railway
  system-types:
    - onboard-software
    - linux
  lifecycle-phases:
    - software-development
    - software-validation
  integrity-levels:
    - SIL-2
  roles:
    - software-developer
    - verifier
  attributes:
    automation-level: GoA4

standards:
  include:
    - EN50716
  exclude: []

selection:
  subject-group-profile:
    id: functional-safety
    version: 1.0.0

  statement-functions:
    - requirement

  primary-subjects: []

  primary-subject-groups:
    - safety-lifecycle
```

Selection dimensions are independent. Missing or empty dimensions do not filter candidates. Within
one active dimension, listed values use OR semantics. Across active dimensions, the analyzer uses
AND semantics **on the same source clause**.

The example therefore means:

```text
statement_function == requirement
AND
primary_subject belongs to subject group "safety-lifecycle"
```

It does not mean "one clause is a requirement and another clause happens to concern the safety
lifecycle."

`primary-subjects` and the subjects expanded from `primary-subject-groups` are combined as one
effective subject set. Subject groups are versioned resources so a policy selection remains
reproducible even when grouping conventions evolve.

A ready-to-edit example is available at
[`examples/governance/rail-onboard-sil2.yaml`](../../examples/governance/rail-onboard-sil2.yaml).

The initial `functional-safety@1.0.0` resource contains:

- `safety-lifecycle`
- `verification-and-validation`
- `configuration-management`

Engineering vocabulary in `context` remains open; canonical Standards Atlas semantic dimensions
and primary-subject identities are normalized and validated.

### Candidate analysis and HITL review

```bash
uv run standards-atlas governance profile select \
  local/governance/rail-onboard-sil2.yaml \
  --document EN50716
```

Default output:

```text
local/review/governance/rail-onboard-sil2/
  candidate-analysis.json
  candidate-analysis.csv
```

Candidate analysis schema version 2 records both the Control-level result and clause-local
evaluation evidence. Every source clause is evaluated against all active semantic dimensions.

Clause result precedence is:

```text
excluded > undetermined > selected
```

That means an explicit mismatch in any active dimension makes that clause non-matching; missing
required evidence keeps it `undetermined`.

Control aggregation is intentionally different:

```text
selected > undetermined > excluded
```

A Control is selected if at least one source clause satisfies all active dimensions. If no clause
matches but at least one could match once missing evidence is resolved, the Control remains
`undetermined`. Only when all relevant clauses explicitly fail the selection is the Control
`excluded`.

The analysis JSON records:

- resolved subject-group profile and effective primary subjects;
- source clauses for every Control;
- clause-local decision and selector signals;
- primary subject and ambiguous subject candidates;
- `matching-clause-ids`;
- `undetermined-clause-ids`.

The CSV is the intended HITL review surface and includes `matching_clause_ids`,
`matching_primary_subjects`, `undetermined_clause_ids`, and detailed reasons. Reviewers can
therefore inspect the exact clause responsible for inclusion or uncertainty instead of reviewing a
Control-level label without evidence.

### Gemara Policy scaffold

```bash
uv run standards-atlas governance profile export-policy \
  local/governance/rail-onboard-sil2.yaml \
  --responsible "Rail Safety Engineering" \
  --accountable "Project Safety Manager"
```

Default output:

```text
local/exports/governance/rail-onboard-sil2/
  policy.yaml
  policy.yaml.scaffold.json
```

Scope, imports, and exclusions are deterministic. RACI contacts are explicit because organizational
responsibility cannot be derived from a technical standard. Evaluation methods, assessment plans,
frequency, evidence requirements, and executor selection remain explicit downstream policy
authoring concerns.

The scaffold sidecar uses schema version 2 and preserves the Selection Profile plus clause-level
selection provenance used to create the draft. In particular it records:

- Candidate Analysis schema version;
- resolved Subject Group Profile and effective primary subjects;
- selected, excluded, and withheld Controls;
- matching Clause IDs and Primary Subjects for selected Controls;
- undetermined Clause IDs and clause-local reasons for withheld Controls.

`undetermined` blocks policy export by default:

```text
candidate analysis contains undetermined controls
    -> no policy scaffold
```

This prevents an incomplete classification from silently becoming policy truth. A reviewer can
inspect the CSV/JSON evidence and improve the profile or the source semantic enrichment.

For authoring experiments where unresolved Controls must remain outside the effective policy, use:

```bash
uv run standards-atlas governance profile export-policy \
  local/governance/rail-onboard-sil2.yaml \
  --responsible "Rail Safety Engineering" \
  --accountable "Project Safety Manager" \
  --withhold-undetermined
```

The generated artifact remains a draft. Undetermined Controls are excluded from the effective
catalog import and listed separately in `policy.yaml.scaffold.json` together with their
clause-local reasons.

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
