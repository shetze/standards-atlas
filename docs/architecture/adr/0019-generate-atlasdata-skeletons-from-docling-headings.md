# ADR 0019: Generate AtlasData skeletons from Docling headings

## Status

Accepted

## Context

Onboarding a new standard previously required manually transcribing its public clause structure into an AtlasData file. This is slow and error-prone, especially for vocabulary standards such as ISO/IEC 27000:2018, where Docling sometimes emits a clause number and its term heading as two adjacent `section_header` items.

The source PDF and Docling extraction are private workspace artefacts. AtlasData is committed to the repository and therefore must contain only distributable structural metadata. Copyright-protected clause bodies must never be copied into the generated file.

## Decision

Standards Atlas provides an `atlasdata onboard-docling` command and an application service that derive an AtlasData skeleton from numbered Docling section headings.

The generator:

- recognizes decimal clause references, including introductory clauses such as `0.1`;
- supports headings where reference and title occur in one item;
- joins adjacent heading items when Docling separates the reference from the title;
- classifies numbered entries below Clause 3 as terms by default;
- emits only the publication year, structure tokens and TOC records;
- generates deterministic TOC hashes;
- excludes clause bodies, notes, tables, figures and other copyrighted content;
- refuses to replace an existing AtlasData file unless `--overwrite` is supplied.

The generated file is a reviewable onboarding artefact, not an unquestionable source of truth. A maintainer must inspect the structure before importing and aligning the standard.

## Consequences

New standards can be onboarded with substantially less manual work while preserving the public/private boundary of the project. The resulting AtlasData file can immediately be processed by the existing document import, normalization, reference detection and alignment pipeline.

The initial classifier intentionally uses conservative conventions. Standards with annexes, requirement subclauses or unusual numbering may require manual edits or future configurable classification rules.

## ISO/IEC 27000:2018

The first generated file is `data/IEC27000`. It contains 128 structural clauses, including introductory clauses `0.1` to `0.3`, Clauses 1 to 5.5.6 and 77 terms from 3.1 to 3.77. The bibliography is not modeled as a clause because it has no numbered AtlasData reference.
