# Structural taxonomy and semantic ontology

Standards Atlas separates deterministic document structure from model-assisted engineering meaning. The production path is intentionally one-way:

```text
EngineeringDocument
        │
        ▼
     TAXONOMY
  deterministic
        │
        ▼
StructuralProfile + StructuralContext
        │
        ▼
     ONTOLOGY
 qualified LLM
        │
        ▼
   SemanticProfile
```

This page is the canonical current-state overview for ADRs 0050, 0051, and 0061 through 0069. Historical ADR terminology remains useful for understanding the evolution, but production ownership follows the model below.

## Structural taxonomy

The `TAXONOMY` workflow stage answers *where a clause belongs and what deterministic structural evidence surrounds it*. It is LLM-free. Versioned structural taxonomy definitions live below `resources/structure-taxonomies/`; Python classifier implementations provide the algorithms and are resolved by taxonomy id and version. YAML defines the category contract rather than a general-purpose rule language.

`StructuralProfile` stores independent taxonomy dimensions such as document section, domain category, annex status, node/leaf role, and other selected taxonomy categories. A clause may therefore be classified along several structural axes without collapsing those axes into a single role.

## Materialized structural context

The taxonomy stage also materializes `StructuralContext`. Semantic classifiers consume this object rather than reconstructing hierarchy from clause prose. Context can include:

- ancestor headings and inherited heading semantics;
- sibling and sequence position;
- contextual-node content;
- structural reference edges;
- explicit scope mentions;
- resolved or deferred structural scope reach.

Ancestor-heading inheritance is structural evidence, not semantic inference. It allows a leaf clause to retain the context established by its containing sections while preserving the leaf's own content and identity.

## Structural scope reach is not semantic applicability

A scope statement can structurally govern another clause without telling us the semantic applicability subtype of that governed clause. Standards Atlas therefore keeps these concepts separate:

```text
structural scope context  !=  semantic applicability
```

Structural scope reach records deterministic relationships such as `this clause`, following siblings, or a scope-heading subtree. The `ONTOLOGY` stage may use that evidence when interpreting applicability, but it must not turn the existence of a scope edge into an automatic applicability label. Observed structural applicability conflicts remain useful qualification evidence.

## Semantic ontology

The `ONTOLOGY` workflow stage answers *what the clause means in the engineering ontology*. The production classifier is selected through qualification and receives clause content plus the already materialized structural context. The current multidimensional semantic profile includes:

- statement functions;
- knowledge kinds;
- process functions;
- applicability functions;
- responsibility functions.

These dimensions are ontology resources versioned independently from the semantic task that composes them. Automatic modal-verb or keyword heuristics outside the ontology stage are intentionally forbidden; reviewed/imported annotations are allowed because they are explicit evidence rather than automatic inference.

## Ownership and inheritance

`ENRICH` constructs canonical content and evidence but does not classify structure or semantics. `TAXONOMY` owns deterministic structural classification and context materialization. `ONTOLOGY` owns automatic semantic interpretation. Publication consumes these results but does not reclassify them.

Defaults and inheritance remain explicit deterministic rules. Core normative sections may inherit normative status; annex declarations determine annex status; notes, examples, and guidance remain informative where the governing standard requires that distinction. Whole informative parts may define a document-level default.

## Qualification boundary

Evaluation and qualification are separate from production classification. Corpora may contain materialized structural context so structure-aware prompts can evaluate the same evidence contract used by production `ONTOLOGY`. Content-only prompts intentionally omit that context and remain useful as a baseline. Qualification selects and validates classifiers; it does not become a hidden production stage.

## Related decisions

- [ADR 0050](adr/0050-model-structural-profiles-as-independent-taxonomy-dimensions.md) introduces independent structural dimensions.
- [ADR 0051](adr/0051-multidimensional-semantic-classification.md) replaces the former one-dimensional semantic-role model.
- [ADR 0061](adr/0061-modular-deterministic-structural-taxonomy-engine.md) defines the modular deterministic engine.
- [ADR 0065](adr/0065-separate-structural-taxonomy-from-semantic-ontology.md) makes the taxonomy/ontology boundary explicit.
- [ADR 0066](adr/0066-structural-context-taxonomy-stage.md) materializes structural context.
- [ADR 0067](adr/0067-production-ontology-workflow-stage.md) establishes production ontology classification.
- [ADR 0068](adr/0068-finalize-taxonomy-ontology-stage-ownership.md) finalizes stage ownership.
- [ADR 0069](adr/0069-materialize-structural-scope-reach.md) materializes structural scope reach.
