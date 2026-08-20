# Structural classification

Standards Atlas separates document structure from statement semantics.

## Structural profile

`StructuralProfile` is attached to each clause and contains independent taxonomy dimensions. Current dimensions include canonical document section, domain category, and annex status, with room for taxonomy identifiers and confidence or provenance metadata. The dimensions may be inferred from headings, hierarchy, document metadata, annex declarations, and domain-specific taxonomies.

This model implements ADR 0050 and replaces the former `Clause.semantic_roles` representation removed by ADR 0051. No compatibility field exists in the clause model.

## Taxonomy to ontology classification flow

![Taxonomy to ontology classification flow](diagrams/svg/taxonomy-ontology-classification-flow.svg)

The deterministic taxonomy stage enriches the normalized `EngineeringDocument` with
`StructuralProfile`, `StructuralContext`, reference edges, and structural scope reach. These
values form explicit evidence for the subsequent ontology stage. They never directly assign
semantic statement, knowledge, process, applicability, or responsibility functions. The
ontology classifier consumes normalized content together with the materialized structural
evidence. `OntologyEngine` validates the emitted dimensions and values against the versioned
ontology profile before `OntologyClassificationService` persists them as
`SemanticClassification`.

The stage boundary is deliberate: taxonomy answers where a clause is located and how
structural statements reach other clauses; ontology answers what the clause means in the
engineering knowledge model.

## Why dimensions are independent

A one-dimensional role cannot faithfully represent that a clause is simultaneously:

- located in a scope or requirements section;
- normative or informative through document/annex context;
- associated with verification, management, development, or another domain category;
- a note, example, definition, requirement, or permission at statement level.

Structural classification therefore answers *where the clause belongs in the document and domain framework*. Semantic classification answers *what its statements do*.

## Taxonomy resources and deterministic engine

Versioned structure taxonomies live below `resources/structure-taxonomies/`, separated into document-level and domain-level definitions. Functional-safety taxonomies may specialize general ISO/IEC document structure without being imposed on railway TSI, Polarion, cybersecurity, or other knowledge domains.

The YAML file is the versioned category contract; classification behaviour is supplied by a `StructuralTaxonomyClassifier` implementation. `StructuralTaxonomyRegistry` resolves those implementations by taxonomy id and version, and `StructuralTaxonomyEngine` composes explicitly selected document/domain classifiers with the generic `StructuralProfileClassifier`. Emitted categories are checked against the corresponding YAML definition.

This layer is deterministic and LLM-free. Complex tree algorithms remain normal Python code rather than being encoded in a general-purpose YAML rule language. Semantic LLM tasks are a separate concern. The current built-in implementation moves ISO/IEC Directives Part 2 classification out of the AtlasData adapter; Railway TSI, Polarion, Functional Safety, and Cybersecurity can provide independent classifiers through the same interface.

## Deterministic semantic routing boundary

Taxonomy evidence can be used before an LLM call without making the taxonomy responsible for
semantic meaning. The routing domain in `application.routing` projects `StructuralProfile`
into a `TaxonomySignalProfile` and evaluates a closed set of deterministic matchers against an
in-memory `RoutingContract`. The result is a `SemanticRoutingPlan` whose task dispositions are
`required`, `preferred`, `optional`, or `skip`.

Routing is an integration policy only. A taxonomy category may make an ontology task more
relevant, but it cannot assign an ontology value. This preserves independent evolution of
taxonomies and ontologies. Routing contracts are versioned independently below
`resources/routing-contracts/` and selected through a `routing_contract` workflow manifest.
The resource declares the taxonomy and semantic-task versions it binds while the manifest only
selects a concrete contract version. When such a manifest is selected, the workflow executes a
separate deterministic `routing` stage immediately after taxonomy. Per-clause signal profiles and
routing decisions are persisted below `.atlas/data/routing/<document>/<contract>/<version>/`
rather than being added to `EngineeringDocument`.

The persisted routing artifact is provenance and execution metadata. It records the exact signals,
matched rule ids, dispositions, reasons, and context hints used for each clause. Slice 3 materializes
those decisions but does not yet condition LLM task execution on them; specialized task execution is
introduced with the semantic-task split.

## Inheritance

Defaults and inheritance are explicit normalization rules. Core normative sections may inherit normative status; annex declarations determine annex status; notes, examples, and guidance remain informative even inside a normative parent where the governing standard requires that distinction. Whole informative parts can define a document-level default.

## Evaluation

Qualification corpora must evaluate each dimension independently and report coverage and confusion per dimension. Proposal interfaces should include insufficient-evidence outcomes instead of forcing a category. Structural evidence may be supplied to a structure-aware prompt, while content-only candidates provide a useful baseline.

## Routed specialized semantic tasks

The active routing contract `functional-safety-semantic-profile:1.1.0` addresses five independent
semantic tasks: statement function, knowledge kind, process function, applicability extraction, and
role-relation extraction. Core classification tasks are required. Applicability and role relations
start with an optional baseline and can be boosted to preferred by deterministic structural evidence.
The routing decision controls whether a task runs; it never supplies an ontology label.

`role-relation-extraction:1.0.0` returns only grounded `role_relations`. Relation-type summary fields
are derived after schema validation and therefore cannot disagree with the extracted relations.
Legacy `semantic-profile-classification:2.2.0` remains available for reproducibility of existing runs.
