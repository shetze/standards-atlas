# Knowledge adoption

Knowledge adoption is the controlled boundary between model proposals and canonical engineering knowledge.

## Canonical enrichment

Clause enrichment currently contains only:

- `applicability`;
- `context_routing`;
- `subject_context`.

Applicability is represented by `ClauseApplicability` with explicit presence and optional `included`/`excluded` polarity. Context routing and subject context remain independent dimensions.

## Canonical engineering knowledge

Accepted engineering knowledge is stored in `EngineeringDocument.knowledge` as:

- `KnowledgeEntity`;
- `NormativeAssertion`;
- source-bound `EvidenceAnchor`;
- adoption provenance.

A model proposal must not become canonical merely because it was generated successfully. Adoption is a separate, auditable step.

## Clean-break policy

The former clause-classification fields are not adoption targets and are not imported from old AtlasData companions. Existing `.atlas` and `local` workspaces from the old model must be rebuilt.

## Applicability adoption

Qualification results that pass the active applicability policy are adopted into `enrichments.applicability`. The qualification input path deliberately ignores already adopted applicability to prevent semantic feedback loops.

## Future assertion adoption

The next semantic slices extend adoption from applicability to individual evidence-backed `NormativeAssertion` proposals. The unit of review is the assertion plus its exact source evidence, not a clause-wide classification vector.
