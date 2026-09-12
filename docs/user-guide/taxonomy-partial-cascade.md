# Taxonomy-backed partial cascade (Slice 5)

`evaluation partial-cascade` connects source-backed decisions, sparse model observations,
attribute acceptance, early exits, archive verification and explicit knowledge adoption.
It is an **opt-in operational path**. The existing full-output qualification workflow and
its manifests keep their behavior. This command is not a completed fresh-repeat qualification.

## Model labels

Execution, successful resume and archive verification use the same model/prompt identity
policy as [partial observations](partial-semantic-observations.md#response-model-identity-and-offline-recovery).
The requested reference remains the voter/cache key; a recognised HF repository label
from RamaLama is retained as reported, not treated as a new model or silently rewritten.
An absent quantization selector is explicitly unverified; a contradictory selector,
different repository or prompt is rejected. Raw response hashes remain unchanged.
The policy does not attest runtime model bytes and does not change acceptance thresholds.

## Acceptance and completion

The command uses the models, stages, generation budgets, confidence thresholds and
Presence-disagreement settings from the selected manifest. It does not relax the Efficient
unanimity rules or qualify additional taxonomy rules. The current source rules can fix a
confirmed term's primary function as `definition`; unreviewed objective and technique rules
remain hints. Historic source labels without independent provenance are not confirmations.

The shared completion profile requires the primary statement function, primary knowledge
kind, Applicability Presence **gate**, and Role Presence. Process attributes become mandatory
when their configured escalation switches require them. The profile and original clause
selection are frozen; the CLI does not expose a reduced-required-attributes switch.
A focused low-level experiment without all four core attributes is explicitly not eligible
for the 80% clause-exit benchmark.

Acceptance is attribute-specific:

- A qualified source decision has a rule, source facts and fingerprints, but no model votes
  or numerical model confidence. A contradictory source remains a conflict.
- A model decision counts only the distinct models that actually evaluated that attribute.
  Failed or unrequested fields and retry attempts never add voters or negative evidence.
- Primary and complete-set decisions are independent. A known primary does not fabricate
  a complete set. A returned set must explicitly contain its constrained primary. Complete
  sets are accepted conservatively using support for the actual selected set, not an invented
  union; this can leave more optional sets open than the legacy label-only aggregation.
- Accepted values retain the original accepting stage and support. Later stages only ask
  open questions. Later disagreement with a frozen value remains diagnostic; a verified
  source conflict cannot be hidden by freezing or voting.

Routing and required-review state consume the same acceptance decisions. Missing cases
remain in the original denominator. `completed_clause_count` measures required cascade
completion; `fully_evaluated_clause_count` separately measures all nine attributes. A clause
can leave the shared cascade with an optional secondary set or role extraction still open.
Do not equate cascade completion with full enrichment or final Applicability-policy completion.

## Plan without models

```bash
uv run standards-atlas evaluation partial-cascade \
  --manifest manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml \
  --run local/evaluation/qualification-run-078.zip \
  --output local/evaluation/taxonomy-efficient/slice-5/run-078
```

Without `--execute`, only the first stage is planned; later selections depend on answers
not yet available. No gateway or model server is started. Every selected clause remains
accounted for even when no observation exists. `--limit 50` freezes a first-50 subset for
both planning and execution; it is neither stratified sampling nor a pending-work limit.

For source-provenance-backed inputs, use `--dataset` instead of `--run`, pointing to a newly
built `dataset.json` as described in [Taxonomy-grounded qualification](taxonomy-grounded-qualification.md).
The command validates dataset/corpus identity against the manifest. Run 078 predates that
source contract: it is useful for missing-evidence and compatibility checks, but it cannot
retroactively supply independent taxonomy confirmations. Its old full-answer votes are
not reinterpreted as new partial observations.

## Execute, resume and archive

Repeat the same command with `--execute` and optionally:

```bash
--archive-output local/evaluation/taxonomy-efficient/slice-5/archives
```

Models are initialized lazily through the existing RamaLama/Codex gateway lifecycle.
A completely reused or empty request population does not initialize a model. All open
attributes for a clause/model are bundled, rather than issuing one request per dimension.
The matrix's provider configuration must be available for a real execution.

The task is `semantic-attribute-observation` 1.0.0; the new prompt is `taxonomy-partial-v2`
with the existing taxonomy frame. Internal request plans/observations use schema 1.1 and
explicitly separate fixed source values, accepted prior-stage constraints and requested
attributes. The standalone Slice-4 v1 path remains readable and unchanged. An accepted
constraint is not an additional independent model answer.

Successful compatible observations are reused and failed cases can be retried. Changed
source, rules, prompt, profile or manifest cannot silently reuse a different run identity.
If repairing an earlier failure changes a later stage's selection or accepted constraints,
a new content-addressed stage revision is created. Old revisions remain auditable and their
actual execution costs remain counted, but they do not create extra voters.

The output contains:

| Artifact | Purpose |
| --- | --- |
| `partial-cascade-plan.json`, inputs/resources snapshots | Frozen source, rules, configuration and profile |
| `stages/...` | Request plans, raw requests/responses, observations, attempts and stage consensus |
| `mixed-consensus-report.json` | Final attribute-specific accepted/open/conflicting decisions |
| `partial-cascade-report.json` / `.md` | Clause completion, review and stage accounting |
| `partial-cascade-costs.json` | Separate cascade, detail-policy and combined measured request costs |
| `policy/...` | Accepted-gate projection, selective detail reports and final policy |
| `policy-history/...` | Preserved policy populations superseded by repaired earlier failures |

Inference failures are retained while other cases continue. Identity corruption, incompatible
configuration and unsafe output paths remain hard errors. Fresh gateway counts are measured
attempts, including retries; cache history is not relabeled as fresh inference. The combined
cost report includes detail-policy executions and preserved revisions. Summed measured gateway
wall time is not the end-to-end process wall clock. Missing provider timing remains unknown.

## Applicability remains a separate final decision

An accepted cascade Presence is a **gate**, not the public Applicability result. With the
policy enabled, the command invokes the existing D4 OR (D3 AND D1) selective detail services
with the manifest's current models, task versions and prompts. No policy definition, subtype
or new Usability output is introduced.

Only accepted gates enter the detail interface. Unknown gates are not converted to false.
A known negative gate needs no detail-model call; a positive gate follows the unchanged
primary/rescue/confirmation routes. Technical detail failures retain three-valued outcomes.
If an earlier repair changes the gate population, old detail reports are archived separately
rather than reused for a different selection. Missing/disabled final policy never makes a raw
gate eligible for public adoption as a final result.

## Verified adoption and public export

`--archive-output` produces the normal checksummed `qualification-run-NNN.zip` envelope and
prints its actual path. The archive records the executed partial task, prompt, models and
configuration, rather than claiming the full-output prompt ran. Before acceptance, the reader
regenerates request plans, checks raw observation identity, replays stage selection/acceptance
and verifies final policy gates, role-specific selections, detail results and provenance.
Supported source rules/task/prompt resources must still match; an incompatible resource
version requires an explicit migration, not best-effort reinterpretation.

Use the existing adoption command with the archive path printed by the execution:

```bash
uv run standards-atlas document adopt-qualification \
  --run local/evaluation/taxonomy-efficient/slice-5/archives/qualification-run-NNN.zip \
  --workspace .atlas/data \
  --output local/review/taxonomy-partial-adoption.json
```

Replace `NNN` with the generated archive number. This is a preview; add `--write` for explicit
canonical adoption. No model is executed and no public companion is written by adoption.
The sparse adoption batch uses internal schema 1.1; legacy 1.0 batches remain supported.
Only accepted values are materialized. Unresolved/unasked attributes keep availability
rather than receiving default negatives. Protected local values and confirmations remain
protected. Deterministic values additionally require the consumed structural facts and
authority to match the current canonical source before any document is written.

Publish separately through the existing exporter:

```bash
uv run standards-atlas atlasdata export-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/data \
  --output local/review/taxonomy-partial-export.json \
  --write
```

A primary may be publicly known while its complete set is unknown. Canonical storage,
JSON roundtrips and companion reads preserve that distinction; explicit known-empty sets
still cannot contradict a known primary. Standalone semantic validation remains strict.
EngineeringDocument and public AtlasData schema versions are unchanged.

The snapshot's publication policy is preserved: `applicability_functions`,
`role_relation_types` and `role_relations` are omitted from public companions. Accepted
structured role details can remain canonical/private, but cannot be reconstructed in a
fresh workspace from public files that deliberately do not contain them. Publicly selected
attributes and their availability roundtrip without invented values.

## Qualification boundary

Synthetic gateway tests and model-free replay establish control flow, serialization and
provenance properties. They do not establish semantic accuracy, the 80% Efficient target or
reduced total cost. The new path requires controlled comparison and the agreed fresh
Applicability qualification before it replaces the default workflow. No threshold changes,
newly qualified taxonomy rules or targeted Slice-6 resolver experiments are activated here.
