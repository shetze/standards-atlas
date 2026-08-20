# ADR 0068: Finalize taxonomy and ontology stage ownership

## Status

Accepted

## Context

ADRs 0065 through 0067 introduced separate structural-taxonomy and semantic-ontology
boundaries and explicit workflow stages. One legacy path remained: the deterministic
`SemanticClassifier` was still called during content enrichment, AtlasData onboarding,
and AtlasData domain mapping. It mixed structural heading classification with
statement-level heuristics such as `shall`, `should`, and `may`.

That violated the intended ownership rule because semantic meaning could be assigned
before the `ONTOLOGY` stage and because one service could perform both structural and
semantic classification.

## Decision

Remove the legacy deterministic `SemanticClassifier` and its production uses.

Stage ownership is now:

- normalization and content enrichment preserve evidence, content, and reference mentions;
- `TAXONOMY` exclusively owns deterministic structural interpretation and materializes
  `StructuralProfile` plus `StructuralContext`;
- `ONTOLOGY` exclusively owns automatic assignment of statement functions, knowledge
  kinds, process functions, applicability functions, and responsibility functions;
- semantic relations produced by reference resolution remain evidence-backed relationship
  data and are not inferred from modal-verb heuristics;
- AtlasData onboarding derives public structure markers only from headings, hierarchy, and
  structural profiles;
- imported public semantic tags remain accepted as explicit annotations rather than being
  re-inferred.

`SemanticClassification` remains in the persisted domain schema for ontology results,
semantic relations, and imported annotations. Legacy structural fields inside that model
may be mirrored by adapters when compatibility requires them, but those values must be
derived from structural evidence and must not become an alternate classification path.

## Consequences

- `ENRICH` no longer performs structural or semantic classification;
- modal verbs no longer create ontology assignments outside the production ontology stage;
- AtlasData skeleton generation remains deterministic and structure-driven;
- the active application architecture has one structural classification path and one
  semantic ontology path;
- qualification remains separate from production ontology classification;
- architecture tests can guard the ownership boundary directly;
- future schema work may remove legacy structural fields from `SemanticClassification`
  without changing stage ownership.

## Related decisions

- ADR 0050: Model structural profiles as independent taxonomy dimensions
- ADR 0051: Multidimensional semantic classification
- ADR 0061: Modular deterministic structural-taxonomy engine
- ADR 0065: Separate structural taxonomy from semantic ontology
- ADR 0066: Structural context taxonomy stage
- ADR 0067: Production ontology workflow stage
