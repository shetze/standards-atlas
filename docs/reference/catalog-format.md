# Catalog format (`catalogs/standards.yaml`)

## Purpose and authority

The catalog is the curated configuration source for standards known to Standards Atlas. It describes document families, physical source documents, classifications, relationships, publication settings, profiles, lineages, and Doorstop hierarchies.

This document is the canonical field-level reference. The checked-in [`catalogs/standards.yaml`](../../catalogs/standards.yaml) is the executable example, while the Pydantic models in `src/standards_atlas/application/catalog/models.py` define the validation contract.

Validate every catalog change with:

```bash
uv run standards-atlas catalog validate catalogs/standards.yaml
```

## Top-level structure

```yaml
version: 2
knowledge_domains: []
industry_sectors: []
families: []
profiles: []
lineages: []
doorstop_hierarchies: []
```

| Field | Required | Meaning |
|---|---:|---|
| `version` | no | Catalog schema version; defaults to `1` |
| `knowledge_domains` | yes | Hierarchical knowledge classifications |
| `industry_sectors` | yes | Hierarchical industry classifications |
| `families` | yes | Standard families or standalone documents |
| `profiles` | no | Named family selections for workflow execution |
| `lineages` | no | Curated relationships across document generations or families |
| `doorstop_hierarchies` | no | Deterministic Doorstop publication trees |

Keys are stable, unique, and filesystem-safe. Parent and target references must resolve within the catalog.

## Knowledge Domains and industry sectors

```yaml
knowledge_domains:
  - key: safety
    name: Safety
  - key: functional-safety
    name: Functional Safety
    parent: safety

industry_sectors:
  - key: transportation
    name: Transportation
  - key: railway
    name: Railway
    parent: transportation
```

Each entry contains `key`, `name`, and an optional `parent`. The catalog validates referenced keys used by family, profile, and lineage classifications.

## Families

A family represents either one standalone source document or a multipart standard.

```yaml
families:
  - key: EN50716
    name: EN 50716
    organization: CENELEC
    publication_year: 2023
    title: Railway applications — Requirements for software development
    source:
      pdf: local/sources/standards/EN50716.pdf
    classification:
      knowledge_domains: [functional-safety, software-engineering]
      industry_sectors: [railway]
    atlasdata:
      path: data/EN50716
      mode: existing
    exports:
      markdown: true
      doorstop:
        enabled: true
        identifier:
          width: 11
```

Required fields are `key`, `name`, and `organization`. A family must define exactly one source shape:

- `source` for a standalone document; or
- `parts` for a multipart family.

Optional metadata includes `publication_year`, `title`, `classification`, `relations`, `status`, `scope`, `atlasdata`, `content_selection`, and `exports`.

## Parts and supplements

```yaml
parts:
  - part: "3"
    key: IEC61508-3
    title: Software requirements
    source:
      pdf: local/sources/standards/IEC61508-3.pdf
    content_selection:
      language: en
      page_ranges:
        - start: 1
          end: 113
    supplements:
      - supplement: "1"
        key: IEC61508-3-1
        document_type: technical-specification
        title: Reuse of pre-existing software elements
        source:
          pdf: local/sources/standards/IEC61508-3-1.pdf
        relations:
          - type: supplements
            target: IEC61508-3
```

Part and supplement keys share one global namespace with family keys. A supplement must declare a `supplements` relation to its owning part.

Supported `document_type` values are:

- `standard`
- `technical-specification`
- `technical-report`
- `amendment`
- `corrigendum`

## Source and content selection

```yaml
source:
  pdf: local/sources/standards/example.pdf
content_selection:
  language: en
  page_ranges:
    - start: 8
      end: 42
  exclude_page_ranges:
    - start: 20
      end: 21
```

Positive page selection can alternatively use a one-based comma-separated `page_list`:

```yaml
page_list: 7,9,11,15-19
```

Use positive selection for alternating bilingual pages when possible, because it makes the retained source set explicit. Page ranges are inclusive. Page numbers must be positive and range ends must not precede starts.

## Classification

```yaml
classification:
  knowledge_domains:
    - functional-safety
    - software-engineering
  industry_sectors:
    - railway
```

Classification references top-level keys. Part and supplement classifications are additive metadata for those physical documents; they do not create new Knowledge Domains.

## Relations

```yaml
relations:
  - type: derived-from
    target: IEC61508
    note: Domain-specific adaptation
```

The target must be a known family, part, or supplement key. Supported relation types are:

`sector-specialization-of`, `derived-from`, `complements`, `depends-on`, `related-to`, `provides-method-for`, `supplements`, `supersedes`, `superseded-by`, `adapts`, `specializes`, and `consolidates`.

Catalog relations are curated document-level knowledge. Clause-level relations are derived and persisted separately in the canonical document model.

## Status and scope

```yaml
status:
  normative_state: current
  effective_from: 2023
  effective_until: null
  retained_for: []
scope:
  sectors: [railway]
  railway_domains: [rolling-stock]
  lifecycle_areas: [software-development]
  note: Optional explanatory text
```

`normative_state` accepts `current`, `superseded`, `withdrawn`, `draft`, or `historical`. When both dates are present, `effective_until` must not precede `effective_from`.

## AtlasData and exports

```yaml
atlasdata:
  path: data/EN50716
  mode: existing
exports:
  markdown: true
  doorstop:
    enabled: true
    identifier:
      width: 11
```

`atlasdata.path` is relative to the project root. Export settings control publication projections and do not alter the canonical `EngineeringDocument`.

## Profiles

```yaml
profiles:
  - key: railway
    name: Railway standards
    families: [EN50126, EN50129, EN50716]
    knowledge_domains: [functional-safety]
    industry_sectors: [railway]
```

Profiles provide named family selections for `workflow plan` and `workflow run`. Every family key must resolve.

## Lineages

```yaml
lineages:
  - key: railway-software-safety
    name: Railway software safety lineage
    members: [IEC61508-3, EN50128, EN50657, EN50716]
    knowledge_domains: [functional-safety, software-engineering]
    industry_sectors: [railway]
```

Lineages capture curated groupings that are not necessarily equivalent to direct relations. Members may reference families, parts, or supplements.

## Doorstop hierarchies

```yaml
doorstop_hierarchies:
  - key: functional-safety
    name: Functional Safety
    root: IEC61508
    families: [IEC61508, EN50126, EN50129, EN50716]
    template: atlas-clean
```

The root must be listed in `families`, and family entries must be unique and resolve to catalog families. A hierarchy is a publication projection, not the canonical Knowledge Domain graph.

## Validation guarantees

Catalog validation rejects at least:

- duplicate family, part, supplement, lineage, or hierarchy keys;
- unresolved classification, profile, lineage, relation, or hierarchy references;
- a family defining both `source` and `parts`, or neither;
- invalid page selections and date ranges;
- supplements without a relation to their owning part;
- Doorstop roots outside their hierarchy family set.

For workflow usage, see [Catalogs and profiles](../user-guide/catalogs-and-profiles.md) and [Getting started](../getting-started/README.md).
