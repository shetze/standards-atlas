# ADR-0027: Preserve Layout and Structural Evidence

## Status

Accepted

## Context

The deterministic document pipeline imports native Docling JSON into an
adapter-neutral `ExtractedDocument` and then transforms it into a
`NormalizedDocument`. Earlier versions retained source page numbers and
bounding boxes through `SourceEvidence`, but discarded other observations
which are necessary to diagnose or deterministically correct extraction
errors.

The EN 50126-1:2017 document exposed three systematic classes of problems:

1. repeated page furniture such as `EN 50126-1:2017 (E)` is inconsistently
   labelled by Docling as `page_header`, `section_header`, or ordinary text;
2. figures and formulae contain important information and relations which
   cannot be reconstructed from plain text alone; and
3. multi-level lists are often emitted as flat list-item sequences even though
   indentation and group membership contain evidence of their hierarchy.

Correcting these problems requires more than the extractor's semantic label.
The pipeline needs the original layout and structural observations. If those
observations are discarded during import or normalization, later deterministic
classifiers must guess and their decisions cannot be audited.

## Decision

The pipeline shall preserve extractor observations separately from normalized
semantic interpretation.

Every extracted item and every independently traceable extracted list item may
carry one or more immutable `LayoutEvidence` records. A record preserves, when
available:

- the native source reference;
- the original content layer;
- the declared parent reference;
- the complete enclosing group path in outer-to-inner order;
- source-page width and height;
- the original marker and original text;
- caption references;
- cross-reference references; and
- footnote references.

`SourceEvidence` remains responsible for source identity, page number,
bounding box, locator, and extraction method. `LayoutEvidence` complements it;
it does not replace it.

The Docling adapter shall resolve the declared body tree while recording the
group path through which each content item was reached. For items omitted from
the body tree, the adapter shall reconstruct the group path from native parent
references when possible.

Caption text may be resolved for immediate use, but the native caption
references must also be retained. The same rule applies to other structural
references: convenience projections must not replace source observations.

Normalization shall copy layout evidence without semantic reinterpretation.
When normalized items merge multiple source items, their layout evidence shall
be concatenated in source order. When a list is retained as a list, both the
list and each normalized list item shall retain the evidence belonging to its
source items.

The `NormalizedDocument` schema version is raised to 4 because the persisted
payload now contains layout evidence.

## Boundaries

This ADR does not define:

- page-header or page-footer classification rules;
- image asset extraction and storage;
- formula transcription or semantic validation;
- reconstruction of hierarchical lists; or
- a general transformation ledger.

Those capabilities shall consume the preserved evidence in later slices and
record their own deterministic decisions.

## Invariants

The following invariants apply:

1. Layout evidence is observational and immutable.
2. Original Docling labels and layout observations are never overwritten by a
   normalized interpretation.
3. Every merge preserves the evidence of every contributing source item in
   source order.
4. Missing optional evidence is represented as absent data, not fabricated
   defaults.
5. Serialized normalized artifacts remain deterministic.

## Consequences

### Positive

- Page-furniture classification can use page-relative geometry and repetition
  without trusting Docling labels blindly.
- List reconstruction can use indentation and group ancestry.
- Figures, captions, formulae, footnotes, and references remain traceable even
  before dedicated domain models are introduced.
- Corrections can later be explained as interpretations of explicit source
  observations.
- Qualification tests can distinguish extractor output from pipeline
  decisions.

### Negative

- Normalized artifacts become larger.
- Schema consumers must accept schema version 4.
- The adapter must understand enough of the Docling reference graph to retain
  ancestry and relations.
- Evidence preservation alone does not improve rendered Markdown; subsequent
  classification and visual-content slices are still required.

## Follow-up

The preserved evidence is the required input for:

1. a deterministic page-furniture classifier;
2. a visual asset and formula contract;
3. hierarchical list reconstruction; and
4. the transformation ledger.
