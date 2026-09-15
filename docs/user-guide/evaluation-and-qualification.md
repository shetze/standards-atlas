# Evaluation and qualification

Standards Atlas separates deterministic document context from qualified semantic inference.
The current production semantic scope is intentionally narrow after the semantic-core refactoring.

## Current qualified semantic tasks

The active qualification paths are:

- **Applicability presence/polarity**: determine whether a clause explicitly carries applicability semantics and, when present, whether the explicit polarity is `included` or `excluded`.
- **Formal semantic knowledge extraction**: propose source-bound engineering entities and normative assertions for the assertion-centred knowledge model.

Structural taxonomy, clause type, normative status, references, context routing and subject context are separate inputs. They are not reconstructed as legacy semantic labels.

## Applicability

Applicability is persisted as `enrichments.applicability` and is independent from other semantic enrichment. Accepted applicability is visible to downstream CBox consumers but excluded from the input fingerprint of a new applicability qualification run so that an accepted result cannot trigger or bias its own re-qualification.

The active qualification manifest is:

```bash
uv run standards-atlas workflow run \
  --task qualification \
  --manifests manifests/standards.yaml,manifests/applicability-presence-qualification-v1.yaml \
  --hierarchy functional-safety \
  --knowledge-domain functional-safety
```

Detailed applicability analysis and evaluation commands remain available under `standards-atlas evaluation`.

## Assertion extraction

The assertion-centred model uses `KnowledgeEntity`, `NormativeAssertion` and `EvidenceAnchor`. Model output is a proposal, not canonical knowledge. Assertions become canonical only through the qualification/adoption boundary and retain source and provenance bindings.

The former semantic-extraction qualification command was removed in Slice 5C together with its entity/relation artifact contract. Assertion proposals are not treated as qualified knowledge until the assertion-centred qualification workflow introduced in Slice 7.

## HITL

The review-package infrastructure is retained as the generic human-review substrate. Legacy taxonomy, role, statement-function, knowledge-kind and process-function review campaigns have been removed. Future review packages should operate on assertion/evidence proposals rather than resurrecting clause-level classification labels.

## Removed legacy dimensions

The following are no longer production semantic dimensions:

- statement functions / primary function;
- knowledge kinds / primary knowledge kind;
- process functions / primary process function;
- role-semantics presence and role relations.

Old manifests, prompts, qualification campaigns, CLI commands and tests for these dimensions are intentionally not supported or migrated.
