# Doorstop document hierarchy

Standards Atlas exports all Doorstop documents below one workspace, by default
`.atlas/doorstop`. Each standard family is rendered into its own child directory.
The workspace itself is the Git working copy so that Doorstop can resolve parent
references across sibling document directories.

The workflow derives a Doorstop parent only from directed structural catalog
relations. The current precedence is:

1. `sector-specialization-of`
2. `derived-from`
3. `specializes`
4. `adapts`
5. `depends-on`

Relations such as `complements`, `related-to`, `supersedes`, and
`superseded-by` do not define containment and therefore do not create a
Doorstop parent. A parent is emitted only when both documents are part of the
same workflow plan, preventing dangling parent references for isolated exports.

For multi-part standards, physical part documents are enriched independently.
Before export, `document compose-family` rebuilds the logical family document
from the enriched physical documents in catalog order. This includes clauses
from separately imported supplements that are not present in the family's
AtlasData master document. Duplicate clause IDs across physical documents are
rejected as ambiguous. Markdown and Doorstop exports consume this composed
family document.

## Supplement part identifiers

AtlasData represents a supplement below a standard part with the ``§``
separator. For example, ``3§1`` denotes supplement 1 of part 3. Doorstop item
identifiers remain numeric: the primary part is formatted with the configured
``partShift`` and ``partDigits`` settings, followed by one two-digit segment for
each supplement level. With ``partShift=1``, ``3§1`` therefore starts with
``0401`` while ordinary part ``31`` starts with ``32``. This preserves a
deterministic, collision-free distinction without changing the AtlasData
volume value.

## Multi-part roots

A composed multi-part EngineeringDocument contains one synthetic structural root clause for
 every physical part. The root uses visible reference `0`, carries the part title, and appears
 immediately before the clauses of that part.

Doorstop levels are qualified with a part-specific root level. For example, part 1 clause 1 is
 exported below root `1` as `1.1`, while part 2 clause 1 is exported below root `2` as `2.1`.
 Supplements use a separate numeric root encoding; with `partShift=1`, AtlasData part `3§1`
 becomes root level `401` and its clause 1 becomes `401.1`.

## Heading precedence

Content enrichment separates structural headings from protected clause content. A heading
 detected in the normalized source becomes the clause title. If the physical source has no
 heading line, the existing AtlasData title remains unchanged and is therefore used as the
 Doorstop header. This preserves curated or generated replacement headings without inserting
 them into the protected text body.

## Clause identification across parts

Doorstop clause metadata must remain globally meaningful for multi-part standards.
The exported `idx`, `atlas-reference`, reference `keyword`, and reference hash are
therefore built from the standard name, physical part, publication year, and
visible clause reference. Supplement separators used internally by AtlasData
are rendered as hyphens; for example part `3§1`, clause `7.4.2` becomes
`IEC 61508-3-1:2010 7.4.2`.

## Parent selection

When several selected catalog relations could become a Doorstop parent, the
most specific relation wins. Lifecycle and dependency relations are considered
before the generic `sector-specialization-of` relation. This prevents every
railway standard from being attached directly to IEC 61508 when a more specific
parent exists. The current railway chain is:

```text
IEC61508
  -> EN50129
    -> EN50657
      -> EN50716
```


## Persisted part roots

Multi-part families use the AtlasData clause ``0`` entry of each physical part as the
publishable Doorstop root. The root is retained when deriving the part document, is
excluded from alignment, survives content enrichment, and is composed back into the
family document before export. ``compose-family`` does not invent replacement roots.

Docling onboarding emits both the structural ``<part>-0`` token and a public TOC record
with the heading ``Part <part>``. Existing AtlasData roots are normalized to that heading
when a part view is derived.

The intended railway hierarchy is:

```text
IEC61508
└── EN50128
    └── EN50657
        └── EN50716
```
