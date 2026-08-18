# Documentation style guide

Documentation is part of the maintained product contract. Changes to commands, formats, architecture, or workflows must update the corresponding documentation in the same slice.

## Document ownership

- **Getting started and tutorials** teach ordered learning paths.
- **User guides** describe concrete operational tasks.
- **Architecture documents** explain boundaries, responsibilities, and rationale.
- **Development documents** explain contribution and extension workflows.
- **Reference documents** define current commands, formats, and terminology.
- **ADRs** preserve architectural decisions and their lifecycle.
- **History documents** preserve obsolete approaches that remain useful as rationale.

Avoid reproducing the same normative information in several sections. Link to the canonical document and add only audience-specific context.

## Lifecycle status

Documents whose validity can change over time should use a compact status block near the beginning:

```text
Status: Current | Experimental | Historical | Deprecated
Applies to: <version, contract, or architecture baseline>
Last reviewed: YYYY-MM-DD
Owner: <area or maintainer role>
```

Use status values consistently:

| Status | Meaning |
|---|---|
| Current | Describes the maintained product or policy |
| Experimental | Active but not yet a stable contract |
| Historical | Preserves rationale and must not be read as current behavior |
| Deprecated | Still available temporarily; replacement and removal path are documented |

ADRs use their own decision status vocabulary and supersession metadata.

## Canonical documents and supporting views

Every maintained fact should have one canonical home. A supporting document may summarize that fact for a different audience, but it must link to the canonical source and must not introduce a competing contract.

Examples:

- exact flags and defaults belong in the CLI reference;
- operator sequences belong in user guides;
- architectural responsibility belongs in architecture documents;
- rationale for accepted choices belongs in ADRs;
- planned work belongs in roadmap documents.

When two documents appear to be equally authoritative, consolidate them or state their boundaries explicitly.

## Review triggers

Documentation review is mandatory when a change affects:

- domain entities, invariants, or terminology;
- persisted artifact schemas or invalidation rules;
- CLI commands, options, defaults, or exit codes;
- catalogs, configuration, or environment variables;
- workflow stages, review gates, or recovery behavior;
- inbound or outbound adapter contracts;
- security, visibility, content-location, or copyright boundaries;
- supported deployment modes;
- roadmap claims that become implemented or obsolete.

The pull request or change description should identify the canonical documents reviewed even when no edit is required.

## Ownership and review cadence

Ownership is by area rather than by individual unless the repository explicitly names maintainers. The responsible area approves changes to its current architecture, reference, and operational documents.

Review time-sensitive documents at least when preparing a release and whenever phrases such as “currently”, “planned”, “initial”, or “future” are touched. Prefer capability tables and roadmap links over unqualified temporal claims.

## Language and structure

- Use descriptive headings and short introductory paragraphs.
- State whether a document describes current behavior, planned work, or historical rationale.
- Prefer concrete names from the code and CLI over informal synonyms.
- Explain intentional omissions in diagrams instead of implying completeness.
- Keep examples internally consistent and executable where practical.
- Use terminology from the glossary; add missing canonical terms there rather than redefining them repeatedly.

## Shell examples

Prefer 80 columns and avoid exceeding 100 columns where practical. Wrap long commands with `\` at semantic boundaries and normally place one option on each continuation line:

```bash
uv run standards-atlas workflow run \
  --manifests manifests/standards.yaml \
  --hierarchy functional-safety \
  --overwrite \
  --keep docling
```

## Links and diagrams

- Use relative links for repository documentation.
- Keep editable diagram sources next to their generated SVGs.
- Reference SVGs from Markdown, not screenshots of editable diagrams.
- Update the diagram catalog when adding or replacing an architectural diagram.
- Validate relative links after moving or renaming documents.
- State the scope and intentional omissions of overview diagrams.

A changed Draw.io source and its SVG export form one documentation change. Do not commit one without the other.

## Historical, deprecated, and superseded content

Do not silently rewrite accepted historical decisions. Mark ADRs as superseded or partially superseded and link to the replacing decision. Move non-ADR descriptions of obsolete implementations to `docs/history/` and label their status prominently.

Deprecated current documentation must name the replacement and expected removal condition. When implementation support is removed, current guides and references must remove the obsolete path in the same slice; rationale may remain only in ADRs or history documents.

## Removal checklist

Before deleting or moving a document:

1. identify its canonical replacement;
2. update all repository links;
3. preserve valuable rationale in an ADR or history document;
4. remove duplicate normative statements;
5. run the relative-link check;
6. include deletions in a changes-only delivery manifest when the delivery format cannot encode them directly.

## Release documentation

Release preparation must review the changelog, versioned references, compatibility guidance, generated diagrams, and public/private content boundary. See [Release and versioning](release-and-versioning.md).
