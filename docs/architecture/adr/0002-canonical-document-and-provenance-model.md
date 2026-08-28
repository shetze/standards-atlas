# ADR 0002: Canonical Document and Provenance Model

## Status
Accepted

## Context
Extraction and publication formats are unsuitable as the long-lived engineering representation. The project needs one canonical document model that preserves both logical structure and evidence lineage.

## Decision
`EngineeringDocument` is the canonical representation of one **physical source document or standard part**.

It owns the engineering structure required by downstream processing, including clauses, headings, structured clause content, source anchors, references, visual/table evidence links, and document identity. Canonical objects preserve private source provenance without requiring publication of source-restricted text.

Canonical construction follows these rules:

- normalized/extracted evidence is losslessly attributable to source locations;
- clause content is constructed from aligned, bounded content ranges rather than unconstrained text inference;
- page starts, terms, headings, list structure, tables, figures, formulas, and references retain source anchors when available;
- deterministic transformations record their lineage and configuration identity;
- inferred semantic artifacts remain outside `EngineeringDocument` unless they become deterministic canonical facts.

A standard family is **not** represented by a synthetic canonical `EngineeringDocument`; family composition is a derived publication view defined by ADR 0006.

## Consequences
All downstream systems can rely on a stable document contract. Provenance may increase artifact size, but avoids hidden reconstruction and makes qualification possible.
