# Catalog Format (`manifests/standards.yaml`)

## Purpose

The `manifests/standards.yaml` file is the central catalog of all standards known to Standards Atlas.

It serves three purposes:

1. **Catalog**

   * Lists all supported standards and standard families.
   * Defines relationships between standards.

2. **Workflow Configuration**

   * Specifies which processing steps are enabled.
   * Provides exporter-specific configuration.
   * Allows the workflow to operate without inspecting AtlasData files.

3. **Knowledge Base**

   * Captures information that is not present in the standards themselves, such as technology lineages or document relationships.

The catalog is therefore a **curated configuration file**. It is **not** generated from AtlasData.

---

# Overall Structure

The catalog consists of several independent sections.

```yaml
version: 1

standards:
  ...

lineages:
  ...
```

Additional top-level sections may be introduced in future versions without changing the semantics of existing entries.

---

# Standards

Each entry in `standards` describes one standard family or one standalone standard.

Example:

```yaml
standards:
  - key: IEC61508
    name: IEC 61508
    organization: IEC
    publication_year: 2010

    exports:
      markdown: true
      doorstop:
        enabled: true
        identifier:
          width: 11
```

---

## key

Unique identifier used throughout Standards Atlas.

Requirements:

* unique
* stable
* filesystem-safe
* used by the CLI

Examples:

```yaml
key: IEC61508
key: ISO26262
key: EN50716
```

The key is the primary identifier used throughout the application.

---

## name

Human-readable standard name.

Example:

```yaml
name: IEC 61508
```

---

## organization

Standards organization.

Typical values:

```yaml
organization: IEC
organization: ISO
organization: CENELEC
organization: ETSI
```

---

## publication_year

Publication year of the standard family.

Example:

```yaml
publication_year: 2010
```

This value is used for display and catalog information.

---

# Export Configuration

The `exports` section contains exporter-specific configuration.

Example:

```yaml
exports:
  markdown: true

  doorstop:
    enabled: true

    identifier:
      width: 11
```

Each exporter owns its own configuration namespace.

---

## Markdown Export

Simple enable/disable flag.

```yaml
exports:
  markdown: true
```

---

## Doorstop Export

Doorstop-specific settings.

```yaml
exports:
  doorstop:
    enabled: true

    identifier:
      width: 11
```

---

### identifier.width

Defines the numeric width of generated Doorstop identifiers.

Example:

```yaml
identifier:
  width: 11
```

The value determines the zero-padded width of generated numeric IDs.

Example:

```
00000000123
```

The width depends on the numbering scheme of the corresponding standard family.

Typical values:

| Standard  | Width |
| --------- | ----: |
| IEC 61508 |    11 |
| ISO 26262 |    12 |
| EN 50716  |     8 |

The workflow automatically forwards this value to the Doorstop exporter.

---

# Lineages

The `lineages` section describes relationships between standards that are not directly encoded in the standards themselves.

Example:

```yaml
lineages:
  - key: cenelec-railway-software-safety

    name: Railway Software Safety

    standards:
      - EN50128
      - EN50657
      - EN50716
```

Lineages allow Standards Atlas to:

* group related standards
* analyse evolution over time
* visualize technology families
* support navigation

These relationships are curated and are **not** generated automatically.

---

# Design Principles

## Stable identifiers

The `key` of a standard must never change once published.

Changing a key invalidates references throughout the repository.

---

## Curated Metadata

The catalog contains metadata that cannot be extracted from standards.

Examples include:

* lineages
* relationships
* exporter configuration
* workflow configuration

Such information should always be edited manually.

---

## AtlasData Synchronization

Some metadata originates in AtlasData.

Currently these values may be synchronized:

* publication year
* Doorstop identifier width

Synchronization should update only the corresponding fields while preserving all manually curated information.

The catalog must never be regenerated wholesale from AtlasData.

---

## Export-specific Configuration

Exporter configuration is isolated inside the corresponding exporter block.

Example:

```yaml
exports:
  markdown: true

  doorstop:
    enabled: true

    identifier:
      width: 11
```

This allows additional exporters to introduce their own configuration without affecting unrelated tooling.

---

# Backwards Compatibility

Existing catalog entries should remain valid whenever possible.

New configuration should be introduced by extending exporter-specific sections rather than changing the semantics of existing fields.

This minimizes migration effort while allowing the catalog format to evolve over time.

