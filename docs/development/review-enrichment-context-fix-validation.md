# Review enrichment/context remediation validation

Date: 2026-09-14

This change closes two gaps in the partial-semantic HITL preparation path.

1. Physical part normalization keeps the canonical AtlasData clause-0 heading as the derived
   document/root title. A manifest title is only a fallback when AtlasData has no root heading.
2. Review preparation reuses the existing `ClauseProvider` for the normalized
   `EngineeringDocument` and stores current review-profile values from `enrichments.semantic.*`
   as `producer_kind=engineering` proposals. They remain proposals, never HITL labels.

No `ReviewSourceSupplementProvider` or second AtlasData truth source is introduced. The review
application layer stays adapter-independent; the CLI composes the existing
`EngineeringDocumentClauseProvider` when the canonical document repository is present.

## Trust boundaries

- Development cases expose current engineering enrichment candidates to Codex and the human
  workbench so the values can be challenged with independent reasoning/evidence.
- Holdout cases withhold current engineering enrichments from MCP reads. The human workbench also
  withholds engineering/model proposals until a recorded source-based first assessment and reveal.
- Historical/reference proposals remain hidden from Holdout even after assistance is revealed.
- Candidate enrichments carry their generated/confirmed provenance but do not create human
  decisions or suite publication authority.
- Clause id, document key, reference, content hash and canonical source structure are checked
  before current EngineeringDocument enrichments are attached. A stale source package is rejected.

## Real-source check

`AtlasDataImportPipeline.import_physical(data/ISO26262, document_key="ISO26262-11", part="11")`
produced:

- document title: `Guidelines on application of ISO 26262 to semiconductors`
- root clause 0 heading: same title
- clause 4.7.6.4 ancestor chain: `4.7.6`, `4.7`, `4`, `0`, with the clause-0 heading above

The checked-in enrichment companion for clause `4.7.6.4` contains the four review-profile
candidate values observed by the user:

- `primary_function = description`
- `primary_knowledge_kind = process`
- `role_semantics_present = false`
- `process_functions = [activity, decision]`

## Automated checks

Completed successfully in the implementation workspace:

- 152 passed, 1 skipped: document selection + review package + workbench + MCP review tests
- 40 passed: review preparation
- 57 passed: review handoff
- 79 passed: R1 schema refactoring
- 138 passed: architecture tests
- 404 passed: schema + filesystem document repository tests
- 477 passed: application services + AtlasData adapter unit tests
- 6 browser tests skipped because the optional browser runtime is not enabled
- `node --check` passed for the modified review-workbench JavaScript
- Python `compileall` passed for source and modified tests

These groups overlap and must not be summed as a project-wide test count. A single full pytest run
was attempted, but this execution environment timed out before completion; no failing assertion was
reported before that timeout. Ruff is not installed in the execution environment, so no Ruff run is
claimed.

## Regeneration boundary

The normalization title fix changes canonical structural context and therefore its bound context
hash. Existing review packages/candidate selections generated from the old `Part N` root are not
silently upgraded. Regenerate the affected normalized part document and the source-only
qualification/corpus input, rebuild the review package, rebuild its candidate index and rerun the
selection materialization. This preserves the source/context integrity guarantees rather than
mixing old frozen context with current enrichments.
