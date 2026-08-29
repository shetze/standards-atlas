# ADR 0003: Document Extraction and Normalization Pipeline

## Status
Accepted

## Goal alignment
Acquisition and normalization establish the evidence foundation of the knowledge-engineering pipeline. Their purpose is not merely text extraction: they must preserve enough structure and source identity for later context construction, qualified semantic analysis, and formal knowledge assertions to remain auditable.

## Context
PDF extraction contains layout noise, repeated furniture, ambiguous references, lists, and tool-specific structures. These concerns must be resolved before canonical document construction without losing source evidence.

## Decision
Docling is the primary PDF extraction adapter, behind a hardened adapter boundary. Its output is converted into an internal normalized document contract before alignment or canonical construction.

The deterministic pipeline is:

```text
PDF -> Docling extraction -> normalized document -> candidate detection -> structural alignment -> EngineeringDocument enrichment
```

Normalization is lossless with respect to usable extracted evidence and may classify or reconstruct structure, including page furniture, headings, lists, code blocks, page anchors, term-definition anchors, and reference candidates. Candidate detection occurs before alignment. Alignment uses AtlasData/document structure and bounded source regions; ambiguity is surfaced for review rather than silently resolved by an LLM.

Manual overrides and full-document Markdown review are permitted as explicit, auditable correction inputs.

## Consequences
Extraction-tool quirks do not leak into the domain model. Deterministic normalization can evolve independently and can be regression-tested against source evidence.
