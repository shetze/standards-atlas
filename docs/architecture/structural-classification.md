# Structural classification

Standards Atlas separates document structure from statement semantics.

## Structural profile

`StructuralProfile` is attached to each clause and contains independent taxonomy dimensions. Current dimensions include canonical document section, domain category, and annex status, with room for taxonomy identifiers and confidence or provenance metadata. The dimensions may be inferred from headings, hierarchy, document metadata, annex declarations, and domain-specific taxonomies.

This model implements ADR 0050 and replaces the former `Clause.semantic_roles` representation removed by ADR 0051. No compatibility field exists in the clause model.

## Why dimensions are independent

A one-dimensional role cannot faithfully represent that a clause is simultaneously:

- located in a scope or requirements section;
- normative or informative through document/annex context;
- associated with verification, management, development, or another domain category;
- a note, example, definition, requirement, or permission at statement level.

Structural classification therefore answers *where the clause belongs in the document and domain framework*. Semantic classification answers *what its statements do*.

## Taxonomy resources

Versioned structure taxonomies live below `resources/structure-taxonomies/`, separated into document-level and domain-level definitions. Functional-safety taxonomies may specialize general ISO/IEC document structure without being imposed on railway TSI, Polarion, cybersecurity, or other knowledge domains.

## Inheritance

Defaults and inheritance are explicit normalization rules. Core normative sections may inherit normative status; annex declarations determine annex status; notes, examples, and guidance remain informative even inside a normative parent where the governing standard requires that distinction. Whole informative parts can define a document-level default.

## Evaluation

Qualification corpora must evaluate each dimension independently and report coverage and confusion per dimension. Proposal interfaces should include insufficient-evidence outcomes instead of forcing a category. Structural evidence may be supplied to a structure-aware prompt, while content-only candidates provide a useful baseline.
