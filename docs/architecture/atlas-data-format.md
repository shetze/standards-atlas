# Atlas Data Format Specification

## Status

Draft

## Purpose

The Atlas Data Format is the legacy source format used by Standards Atlas to describe the clause-based structure of technical standards in a compact, manually editable form.

The format is intentionally concise. It allows maintainers to model the table of contents, clauses, requirements, objectives, terms, annexes, and text placeholders of standards without copying full copyrighted standard content.

This specification documents the current format so that it can be parsed by the new Standards Atlas architecture without executing the data files as shell scripts.

## Design Goals

The format is designed to support:

* compact manual entry of standard document structures,
* representation of multi-part standards,
* stable generation of internal item identifiers,
* initialization of titles and short text snippets,
* mapping between items from different standards,
* future migration into a canonical domain model.

The format is not intended to store full standard documents.

## File Types

The `data/` directory currently contains three relevant kinds of files:

```text
data/<STANDARD_KEY>
data/mapping*
data/relations.csv
```

Standard files describe one standard or one standard family.

Mapping files describe traceability links between standards.

`relations.csv` defines relationship types used by the mapping layer.

## Standard Data Files

A standard data file consists of three sections:

```text
metadata header
structure block
item initialization data
```

Example:

```text
parent="IEC61508"
digits=8
partShift=0
partDigits=0
name="EN 50716"
oyr=2023

structure=(
 "2023 {1..3} s1.{1..10} 3.1 t3.1.{1..44}"
)

#---data---#
TOC;<hash>;EN 50716:2023 1;Scope;u
TEXT;<hash>;EN 50716:2023 1.1;Short text;u
```

## Metadata Header

The metadata header defines how the standard should be interpreted and how identifiers should be generated.

### Required Fields

```text
name="<standard display name>"
digits=<integer>
```

### Optional Fields

```text
parent="<parent standard key>"
partShift=<integer>
partDigits=<integer>
oyr=<year>
```

### Field Semantics

| Field        | Meaning                                                     |
| ------------ | ----------------------------------------------------------- |
| `name`       | Human-readable standard name, for example `EN 50716`        |
| `parent`     | Optional parent standard family                             |
| `digits`     | Number of digits reserved for generated numeric identifiers |
| `partShift`  | Numeric offset applied to part or volume numbers            |
| `partDigits` | Number of digits reserved for part or volume numbers        |
| `oyr`        | Official publication year of the standard                   |

The parser must treat metadata as declarative data. It must not execute the file as shell code.

## Structure Block

The structure block defines the clause structure of a standard.

```text
structure=(
 "<structure line>"
 "<structure line>"
)
```

Each structure line describes one standard part, volume, or document segment.

A structure line consists of whitespace-separated structure tokens.

Example:

```text
"2023 {1..3} s1.{1..10} 3.1 t3.1.{1..44} 4 4.{1..11} r5.1.2.{1..12}"
```

## Structure Token Syntax

A structure token has the following general form:

```text
[volume-][type][enum:]index[.{range}]
```

Examples:

```text
1
1.1
s1.1
t3.1.{1..44}
r5.1.2.{1..12}
10:A
12:C.2.4.{1..4}
0-4.+{1..133}
8-r11.4.7.{1..4}
```

## Token Components

### Volume Prefix

For multi-part standards, a token may start with a volume or part prefix:

```text
<volume>-
```

Example:

```text
8-r11.4.7.{1..4}
```

This describes requirement items in volume or part `8`.

For single-part standards, the volume prefix may be omitted.

### Type Prefix

A token may contain a type prefix before the clause index.

Currently recognized type prefixes are:

| Prefix | Meaning                             |
| ------ | ----------------------------------- |
| `r`    | Requirement                         |
| `s`    | Scope item                          |
| `t`    | Term or definition                  |
| `o`    | Objective                           |
| `c`    | Clause                              |
| `m`    | Mapping or miscellaneous annex item |

If no type prefix is present, the item is treated as a generic table-of-contents item.

### Enumeration Prefix

Annexes and other non-numeric sections may be mapped into the numeric identifier space using an enumeration prefix:

```text
<enum>:<index>
```

Examples:

```text
10:A
12:C
13:mD
```

The enumeration prefix assigns the non-numeric section to a numeric position for stable identifier generation.

### Clause Index

The clause index represents the visible reference inside the standard.

Examples:

```text
1
1.1
5.1.2
A
C.2.4
```

The clause index may contain numeric and alphabetic segments.

### Ranges

A token may contain a range expression:

```text
{<start>..<end>}
```

Examples:

```text
{1..3}
1.{1..10}
r5.1.2.{1..12}
```

The parser expands these into individual items.

Example:

```text
r5.1.2.{1..3}
```

expands to:

```text
r5.1.2.1
r5.1.2.2
r5.1.2.3
```

### Three-Digit Range Marker

The special `+` marker indicates that the following range should be represented using three digits in the generated identifier.

Example:

```text
0-4.+{1..133}
```

This is used for structures where a large number of paragraph-like items must be represented under a single clause.

The `+` marker affects identifier generation only. It does not change the visible clause reference.

## Item Types

The parser must normalize item types into the following internal values:

| Prefix | Internal Type |
| ------ | ------------- |
| none   | `toc`         |
| `r`    | `requirement` |
| `s`    | `scope`       |
| `t`    | `term`        |
| `o`    | `objective`   |
| `c`    | `clause`      |
| `m`    | `misc`        |

Unknown prefixes must be rejected unless explicitly enabled by compatibility mode.

## Item Initialization Data

The item initialization section starts after:

```text
#---data---#
```

Each following non-empty, non-comment line is a semicolon-separated record.

```text
<KIND>;<HASH>;<REFERENCE>;<CONTENT>;<TYPE>
```

Example:

```text
TOC;44d1cf377dc91798141c1fca214c6e39;EN 50716:2023 1;Scope;u
TEXT;abc123;EN 50716:2023 1.1;Short description;s
```

## Initialization Fields

| Field       | Meaning                                                |
| ----------- | ------------------------------------------------------ |
| `KIND`      | Either `TOC` or `TEXT`                                 |
| `HASH`      | MD5 hash of the reference value                        |
| `REFERENCE` | Full standard reference or generated item UID          |
| `CONTENT`   | Title, heading, short description, or placeholder text |
| `TYPE`      | Item type marker used by legacy tooling                |

## Initialization Record Types

### TOC

`TOC` records initialize titles or table-of-contents entries.

### TEXT

`TEXT` records initialize body text or descriptive placeholder text.

## Hash Field

The hash field is retained for compatibility with existing tooling.

The current convention is that the hash is derived from the value of the reference field.

New tooling should not treat the hash as the primary identifier. The canonical identifier should be derived from the parsed standard reference.

## Standard References

A standard reference identifies a clause or item in a human-readable form.

Examples:

```text
EN 50716:2023 5.1.2.1
ISO 26262-1:2018 3.1
IEC 61508-3:2010 7.4.2
```

The parser should preserve the original reference string and additionally derive a normalized internal identifier.

## Mapping Files

Mapping files describe traceability links between items from two standards.

A mapping file consists of:

```text
mapping metadata
mapping records
```

Example:

```text
from=EN50657
to=EN50128
type=terms
note="EN50657 is inheriting most definitions from EN50128"

3010100;assessment;assessment;3010100
```

## Mapping Metadata

| Field  | Meaning                    |
| ------ | -------------------------- |
| `from` | Source standard key        |
| `to`   | Target standard key        |
| `type` | Relationship category      |
| `note` | Human-readable explanation |

Legacy shell constructs such as `while read`, `do`, `done`, and heredoc markers are compatibility artifacts and must not be part of the canonical parser model.

The parser should extract only metadata and mapping records.

## Mapping Records

Mapping records are semicolon-separated.

```text
<SOURCE_ID>;<SOURCE_LABEL>;<TARGET_LABEL>;<TARGET_ID>
```

| Field          | Meaning                     |
| -------------- | --------------------------- |
| `SOURCE_ID`    | Source item identifier      |
| `SOURCE_LABEL` | Human-readable source label |
| `TARGET_LABEL` | Human-readable target label |
| `TARGET_ID`    | Target item identifier      |

The labels are useful for review and traceability but must not be used as canonical identifiers.

## Parser Requirements

A compliant Atlas Data Format parser must:

* read metadata without executing shell code,
* parse all structure lines,
* expand range expressions,
* preserve the order of generated items,
* normalize item types,
* parse initialization records after `#---data---#`,
* parse mapping metadata and mapping records,
* preserve unknown but syntactically valid metadata fields,
* reject malformed structure tokens with actionable error messages.

## Compatibility Requirements

For PR2, the parser should support the existing files in `data/` without requiring a format migration.

The parser may ignore comments and legacy shell-only constructs.

The parser should support compatibility mode for known legacy irregularities.

## Canonical Internal Representation

The parsed data should be converted into a canonical internal model.

At minimum, the model should include:

```text
StandardDefinition
ClauseDefinition
InitializationRecord
MappingDefinition
MappingRecord
```

The legacy data format should be treated as an import format, not as the internal model of Standards Atlas.

## Non-Goals

The Atlas Data Format does not aim to:

* store complete copyrighted standard text,
* replace official standards documents,
* model all semantic relationships directly,
* act as the long-term canonical storage format,
* encode tool-specific data for Doorstop or BASIL.

## Future Direction

The legacy Atlas Data Format may later be complemented or replaced by a canonical YAML or JSON representation.

However, such a migration should happen only after a stable internal domain model and Traceability API exist.

Until then, the existing compact format remains the preferred manual authoring format for standard structures.

