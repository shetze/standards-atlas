# Context adoption

Context adoption is the controlled, LLM-free boundary that accepts qualified interpretation context into canonical clause enrichments. It is deliberately separate from the future adoption of assertion-centred engineering knowledge into `EngineeringDocument.knowledge`.

## Canonical context enrichments

Clause enrichment currently contains only:

- `applicability`;
- `context_routing`;
- `subject_context`.

Applicability is represented by `ClauseApplicability` with explicit presence and optional `included`/`excluded` polarity. Context routing and subject context remain independent dimensions.

The versioned application contracts are `ContextAdoptionBatch` and `ContextAdoptionReport`, and the mutation boundary is `ContextAdoptionService`. Qualification remains read-only; the service validates source coordinates, content hashes and source-structure requirements before any canonical write.

## Canonical engineering knowledge

Accepted engineering knowledge is stored separately in `EngineeringDocument.knowledge` as:

- `KnowledgeEntity`;
- `NormativeAssertion`;
- source-bound `EvidenceAnchor`;
- adoption provenance.

Model proposals do not enter this model through context adoption. Assertion/entity review and adoption are introduced by the later HITL/canonical-adoption slice.

## Clean-break policy

The former clause-classification fields are not context-adoption targets and are not imported from old AtlasData companions. Existing `.atlas` and `local` workspaces from the old model must be rebuilt.

## Applicability adoption

Qualification results that pass the active applicability policy are adopted into `enrichments.applicability`. The qualification input path deliberately ignores already adopted applicability to prevent semantic feedback loops.
