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
semanticProfile="<profile-id>:<profile-version>"
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
| `semanticProfile` | Optional versioned semantic profile for public semantic TOC tags |

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
The first token defines the release context for the rest of the structure tokens, it is the year of the publication of that part or volume.

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
r12:C.2.4.{1..4}
b9:A.{1..10}
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
| `b`    | Table                               |
| `m`    | Mapping or miscellaneous annex item |

If no type prefix is present, the item is treated as a generic table-of-contents item.

### Table numbering and structural location

For a `b` token, the final index component is the declared table number, not
an ordinal local to its containing clause. Main-body table labels use that
number alone within each physical part. Annex table labels combine the annex
letter with that final number. Intermediate components retain the structural
location used to resolve the containing clause.

| Structure token | Public table reference | Structural parent |
| --- | --- | --- |
| `1-b7.1.2.2.1` | `IEC 61508-1:2010 Table 1` | `7.1.2.2` |
| `1-b8.2.18.5` | `IEC 61508-1:2010 Table 5` | `8.2.18` |
| `2-b9:A.2.14` | `IEC 61508-2:2010 Table A.14` | `A.2` |
| `2-b9:A.3.15` | `IEC 61508-2:2010 Table A.15` | `A.3` |
| `2-b10:B.{1..6}` | `IEC 61508-2:2010 Table B.1` through `B.6` | `B` |

The examples assume that the indicated parent clauses are declared. Import
otherwise resolves the nearest existing structural ancestor, unless a `TABLE`
record explicitly supplies a parent. It does not infer the parent from the
shortened public table label.

The final number is preserved rather than recomputed from encounter order.
This supports partial declarations and numbering gaps. An index of `0`, such
as `b9:A.0`, denotes a table without a caption and without a List-of-Tables
entry. Keep its `b` declaration and structural parent for normalization and
alignment; an empty caption is not a reason to discard it. A `TABLE` record
may represent it, with an empty caption field. No `TABLEINDEX` record is
inferred from the declaration. The enumeration prefix (`9:` or `10:` above) is not part of
the public table number. Different parts can each declare `Table 1`, and
different annexes can each start their own sequence.

`TABLE` and `TABLEINDEX` records use these public labels. `TABLE` stores the
containing clause reference in **field 4**, followed by the optional,
human-reviewed caption in **field 5**. `TABLEINDEX` retains its existing
caption-in-field-4 and `i`-in-field-5 layout. For example:

```text
TABLE;<hash>;IEC 61508-1:2010 Table 1;7.1.2.2;<caption>
TABLE;<hash>;IEC 61508-2:2010 Table A.15;A.3;<caption>
TABLEINDEX;<hash>;IEC 61508-2:2010 Table A.15;<caption>;i
```

#### TABLE field layout and migration

```text
TABLE;<hash>;<table-reference>;<parent-clause-reference>;<caption>
```

The parent is a local clause reference within the table's physical part, not
a heading. Both fields may be empty. Captions can be entered at the end of the
record without editing generated parent metadata. Internally,
`InitializationRecord.content` still means the caption and `type_marker` still
means the parent for `TABLE`; the shared parser/serializer owns the field-order
conversion. Domain models, table IDs and reference-derived hashes do not change
because of the column swap.

Writers add this comment inside the data section when it contains `TABLE` records:

```text
# table-record-layout: parent-caption
```

Keep the generated comment. It makes reimport unambiguous even when the caption
itself looks like a reference (for example `7.1` or `A`) or the parent is empty.
The comment applies only to `TABLE`; other record types and optional semantic
fields keep their previous layout. Both TOC refresh and semantic-annotation
updates use this serializer; Docling onboarding emits the same layout and comment.

For unmarked files the importer accepts the old `caption;parent` and new
`parent;caption` layouts: a sole reference-shaped field is interpreted as the
parent, and a sole free-text field as the caption. Two populated fields that
are both reference-shaped, or neither reference-shaped, are ambiguous and are
rejected rather than silently swapped. Before migrating an unmarked legacy
file with reference-shaped captions (including captions with no parent), add:

```text
# table-record-layout: caption-parent
```

A new-format hand-maintained file can instead declare `parent-caption`.
`atlasdata generate-toc --write` then emits the canonical layout and comment,
with the existing numbered-backup behavior. Do not mix column layouts under
one explicit layout comment. In ordinary generated legacy records such as
`TABLE;...;...;;7.1.2.2`, no preparatory edit is required.

#### Table reference aliases

Existing records using the old complete structure path are recognized as
aliases only where a matching `b` declaration in the same part proves the
mapping. Import merges them with any already-canonical records; canonical
non-empty fields take precedence, while empty fields preserve available
legacy captions and explicit parents. Records without a matching declaration
are preserved, not guessed or renumbered. Regenerating with `atlasdata
generate-toc --write` writes canonical references and recomputes their hashes.

Table IDs are derived from standard, part, edition and canonical table number,
not from the containing clause. A physical-part projection selects tables by
parent clause ID and linked List-of-Tables entries by table ID, never by a
potentially repeated table label. Unassigned tables and unlinked index entries
remain in the family master rather than being assigned to a part by guesswork.

### Enumeration Prefix

Annexes and other non-numeric sections may be mapped into the numeric identifier space using an enumeration prefix:

```text
[type]<enum>:<index>
```

Examples:

```text
10:A
r12:C
m13:D
```

The enumeration prefix assigns the non-numeric section to a numeric position for stable identifier generation. When an item type is present, the historical and canonical order is type prefix first, followed by the numeric enumeration prefix:

```text
r11:C.1
c5:A.2
m13:D
```

For compatibility with AtlasData files produced by an intermediate implementation, readers also accept the reversed spelling:

```text
11:rC.1
5:cA.2
13:mD
```

Writers and generators must always emit the canonical historical spelling.

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
The following generic layout applies to text/TOC records and `TABLEINDEX`;
`TABLE` uses the parent-before-caption layout documented above.

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


## Public Semantic Annotations

TOC records may contain an optional sixth field with publishable semantic
annotations. The field is a comma-separated list of namespaced taxonomy codes:

```text
TOC;<hash>;<reference>;<heading>;<type-marker>;<semantic-tags>
```

Example:

```text
TOC;...;IEC 61508-2:2010 7.4.2;Software requirements;r;SP-REQ,SS-PRE,KK-PRC,RR-ASR
```

The five-field legacy form remains valid. Semantic tags do not contain clause
text, model confidence, rationale, or other evaluation provenance. They express
only reviewed semantic facts suitable for publication.

The namespaces are:

| Namespace | Meaning |
| --------- | ------- |
| `SP` | primary statement function |
| `SS` | secondary statement function |
| `KK` | knowledge kind |
| `PF` | process function |
| `AF` | applicability function |
| `RR` | role relation type |
| `DS` | document structure |
| `NS` | normative status |

The three-letter category codes are owned by the versioned ontology dimension,
not by the AtlasData parser. A file containing semantic tags must declare the
profile used to interpret them:

```text
semanticProfile="functional-safety:1.0.0"
```

Absence of an `AF-*` or `RR-*` tag represents no accepted positive
applicability or role-relation category. `unspecified` normative status is not
serialized as a semantic tag.

### Applying Reviewed Annotations

Reviewed annotations are persisted through a separate text-free manifest so
that protected clause content never has to be committed with the gold labels:

```yaml
schema_version: "2.0"
semantic_profile: functional-safety:1.0.0
annotations:
  - reference: IEC 61508-2:2010 7.4.2
    primary_statement_function: requirement
    secondary_statement_functions:
      - prerequisite
    knowledge_kinds:
      - process
    role_relation_types:
      - responsible_for
```

Apply the manifest with a dry run first:

```bash
uv run standards-atlas atlasdata apply-semantic-annotations \
  data/IEC61508 local/evaluation/reviewed-semantic-annotations.yaml
```

Persist it explicitly with `--write`:

```bash
uv run standards-atlas atlasdata apply-semantic-annotations \
  data/IEC61508 local/evaluation/reviewed-semantic-annotations.yaml \
  --write
```

`generate-toc` preserves existing semantic tags but never promotes inferred or
model-generated classifications to published gold automatically. This keeps the
publication boundary explicit: only the reviewed annotation manifest can add or
replace public semantic tags.

## Accepted enrichment companions (schema 1.2)

The existing structural text grammar and reviewed TOC tags remain unchanged. Accepted canonical
attributes may additionally be persisted in `<AtlasData parent>/enrichments/<physical-key>.yaml`
using `atlasdata export-enrichments`. This is an explicit transport contract, not a canonical
CBox database or an automatic promotion to reviewed semantic tags.

### Document and clause identity

| Field | Meaning |
| --- | --- |
| `manifest_type`, `schema_version` | `atlasdata-enrichments`, string `"1.2"` |
| `document_key`, `family_key` | Exact manifest-declared physical document and family |
| `atlasdata_file`, `selection_part`, `publication_year` | Explicit owning source basename, part selection and manifest edition; unspecified supplement year stays null |
| `fingerprints.structure` | SHA-256 of selected structural clause IDs, references, headings, types and parents; reviewed semantic tags are excluded |
| `clauses[].clause_id`, `.reference` | Stable clause ID and complete canonical `StandardReference` |
| `.atlasdata_md5` | Exact legacy MD5 from the existing AtlasData `TOC` record; a foreign-key reference, not a recomputed fingerprint |
| `.heading` | Internal/canonical heading text used by the enriched document |
| `.fingerprints.heading` | SHA-256 of the internal heading |
| `.fingerprints.atlasdata_heading` | SHA-256 of the reviewed AtlasData heading; need not equal the internal heading |
| `.fingerprints.content` | SHA-256 of available local `plain_text`; omitted when not available |
| `.fingerprints.attributes.<path>` | Attribute-specific evidence, decision-source and private-store fingerprints |
| `.attributes[]` | Selected, typed attribute records; unselected fields and clauses are retained |

All fingerprint values use `sha256:<64 lowercase hex>` syntax. Heading/content fingerprints use
UTF-8 bytes without another normalization step. The structure digest uses deterministic compact
sorted JSON. The `atlasdata_md5` remains the exact 32-hex legacy TOC identifier and is verified
against the current AtlasData file on export and import. Clause records are serialized in physical
document order, not by hash-derived `clause_id`. Duplicate keys, IDs, full references, attribute
paths, unknown fields, unsupported schema versions, contradictory semantic groups and raw private
provenance in the public contract are rejected. Public semantic values are validated against
existing canonical field types, not an independently defined vocabulary.

### Attribute records

Each record contains `path`, `origin`, `value` and the appropriate provenance.
Paths address primary/secondary statement, knowledge and process categories, Applicability
presence/functions, role presence, whole subject context or whole context routing. Role details
(`enrichments.semantic.role_relations` and `enrichments.semantic.role_relation_types`) remain
canonical fields but are temporarily excluded from publication, regardless of value or origin.
The same exclusion applies to their fingerprint entries. Existing schema-1.2 fields remain
readable, but every writer omits them.
`origin` is `generated`, `confirmed` or `unattributed`. Known availability is the default and is
omitted from YAML for readability. `availability: unknown` remains explicit; absence of an
attribute means not assessed, not false. Unknown has a null value, no invented category and
explicit generated assessment metadata. Known false and known empty lists are retained as real
decisions.

`generated` retains generator, method and decision metadata but does not duplicate the enclosing
attribute path or known/unknown state. Evidence strings and `DecisionSupport.source_sha256` are
serialized under `fingerprints.attributes.<path>.evidence` and `.decision_source`. `confirmed`
retains explicit authority without duplicating the enclosing path. Populated unmarked legacy values
are retained as `unattributed`, not promoted. An omitted attribute never clears a value.

Statement/knowledge/process values, Applicability classifications and role presence are public
categorical values. `fingerprints.attributes.<path>.private_value` addresses source-bearing
contexts in the private store; existing private role blobs remain unchanged but are not newly
published or referenced by companion exports.
For these fields, `value` is a bounded view: accepted normalized subject/confidence only; unresolved
subject ambiguity candidates are working state and are omitted from companions. Routing values carry scope reach and counts of conditions/exclusions/qualifications plus reference
coordinates/roles. Deferred role details publish neither a tuple count nor relation types.
The public view never contains source evidence, reference titles, scope prose or raw role actor/target
text. Explicit reference and scope coordinates are resolved against the
physical document before accepting an ID. Deterministic structural scope edges may correct stale
reach labels, but a provider-supplied ancestor ID alone cannot replace an explicit subclause.
`Annex G` must not be rewritten into a self-reference just because the model copied the source ID.
Lists and bounded same-level ranges expand only when all targets resolve uniquely. Unresolved,
partial or ambiguous local groups retain their citation text with a null clause ID. Source-grounded
private evidence can repair an already overwritten canonical reference; ambiguous or unverified
conflicts require review. Protected routing is not normalized on export. The corrected generated
public projection and private value are consistent. These public semantic labels and coordinates are
deliberately published.
`fingerprints.attributes.<path>.private_provenance` optionally binds the original unredacted
provenance.

Publication cleanup removes previously exported role-detail attributes and their fingerprints
from the whole selected companion, including clauses/dimensions outside a partial value update.
This is reported as `omitted`, with the normal dry-run and explicit-write safeguards. All other
attributes and their authority remain subject to the existing merge. Empty public records are
omitted, but canonical clauses, role values, provenance and private blobs are not deleted. Role
presence keeps its true/false/unknown distinction; missing positive details must not be interpreted
as a completed negative extraction. Canonical schema 9, companion schema 1.2 and private evidence
schema 1.0 are unchanged. Reviewed `RR` TOC tags are unaffected.

### Restore and preservation

`atlasdata import-enrichments` validates physical ownership, baseline and clause fingerprints,
then uses the canonical group-wise merge. Current reviewed TOC tags participate on every restore,
even with existing canonical documents. Generated values cannot replace protected confirmations;
contradictory explicit confirmations fail before writes. Unselected state and structural lifecycle
remain unchanged. A source-free structural skeleton may use its AtlasData heading and reports
content as unverified. It does not recreate the copyrighted clause text.

Private blobs are immutable `knowledge-evidence` JSON schema `1.0`, addressed by the SHA-256 of
compact, key-sorted UTF-8 JSON with a final newline. `kind` distinguishes `value`, `generated` and
`confirmed`; `path` and `value` bind the payload. Restore validates the blob hash, kind, path and
public projection. An absent source-bearing value is deferred, not replaced by empty context.
An absent raw provenance blob leaves public metadata/hash references and a diagnostic. Strict
mode rejects either absence. An explicitly referenced canonical empty context can be reconstructed
without private evidence when its exact blob digest verifies that value.

Commands default to dry-run. Explicit writes use all-document preflight, atomic replacement per
file and deterministic output; this is not an all-files transaction. An optional local JSON
`atlasdata-knowledge-report` schema `1.0` gives selected keys, changed/written targets, source-content
verification counts and per-attribute changes. It does not embed private values. Operational
commands and backup/restore instructions are in [AtlasData enrichments](../user-guide/atlasdata-enrichments.md).
