# ADR-0030: Hierarchical List Reconstruction from Layout Evidence

## Status

Accepted

## Context

Docling identifies individual list items reliably in many standards documents, but often
flattens nested list structures. In EN 50126-1 the intended hierarchy remains observable
through horizontal indentation, marker changes, source order, and group lineage. Rendering
all observed items at one level changes the logical meaning of definitions, conditions, and
requirements.

Slice 3.3.1 preserved the layout and structural observations needed to reconstruct this
hierarchy. The normalized contract already permits nested list items, but the normalizer did
not populate their `children` relation.

## Decision

Standards Atlas reconstructs list hierarchy during normalization, before engineering-content
and Markdown rendering.

The deterministic classifier:

1. preserves the original source order;
2. derives stable indentation bands from the left edge of source bounding boxes;
3. treats positions less than six document units apart as the same indentation band;
4. attaches an item to the nearest preceding item at the immediately shallower level;
5. falls back to a flat list when fewer than two reliable indentation bands exist;
6. preserves marker kind, source identities, and layout evidence for every item;
7. records the resulting depth in each normalized list item.

A nested item also records whether its own marker is ordered. This permits mixed structures,
for example an ordered outer list with unordered children, without inferring the child marker
from the parent list.

## Consequences

Markdown and other exporters receive a semantic tree rather than layout-dependent flat
items. The canonical engineering model retains this tree while remaining independent of
Markdown syntax.

The algorithm intentionally prefers a flat result when geometry is absent or ambiguous. It
does not infer hierarchy merely because a parent line ends with a colon. Such linguistic
signals may be added later as supporting evidence, but must not override contradictory
layout evidence.

The current decision does not reconstruct lists split by intervening non-list content, nor
does it merge unrelated lists solely because their indentation matches.
