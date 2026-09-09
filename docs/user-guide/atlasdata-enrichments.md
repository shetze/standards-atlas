# Persisting accepted CBox attributes in AtlasData

`document adopt-qualification` selects existing results into canonical documents. The separate
commands below persist those selected attributes in the AtlasData area and restore them without
new LLM calls. They do not change the qualification policy, infer missing process functions,
reclassify polarity, or render a CBox. The canonical repository remains schema **9**.

## Storage and authority

Physical document ownership comes from `manifests/standards.yaml`, not filename parsing. For
example, the `ISO26262-11` part of `data/ISO26262` has this public companion:

```text
data/ISO26262
data/enrichments/ISO26262-11.yaml
```

The companion is an `atlasdata-enrichments` manifest, schema `1.0`. Its values use the canonical
semantic vocabulary and explicit primary labels. It preserves generated/confirmed/unattributed
origin, availability, decision support and reference identity. **A generated value stays generated
when written into or read from AtlasData.** Existing reviewed TOC tags remain authoritative; two
conflicting explicit confirmations abort rather than silently choosing one.

Source-based structural data, headings, tags and the structural file's `proposed/reviewed/published`
status are never changed by these commands. They extend the existing import pipeline and use the
same attribute-group merge as canonical adoption, rather than introducing another CBox database.

## Preview and export

Run from the project root, after adoption or another canonical enrichment has produced attributes:

```bash
uv run standards-atlas atlasdata export-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/data \
  --output local/review/atlasdata-knowledge-export-preview.json
```

Without a selector, export addresses existing, manifest-declared physical canonical documents.
It does not export synthetic family sources. With `--family ISO26262`, all declared physical
members of that family must exist. `--document ISO26262-11` selects one physical document;
`--document` and `--family` can both be repeated.

```bash
uv run standards-atlas atlasdata export-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/data \
  --output local/review/atlasdata-knowledge-export-applied.json \
  --write
```

The default is a dry run: neither companion files nor private evidence blobs are written.
An explicitly requested local report is still produced. `--write` is the only mutation switch.

`--dimension` restricts export to complete coupled attribute groups and is repeatable:
`statement_functions`, `knowledge_kinds`, `process_functions`, `applicability`, `role_semantics`,
`subject_context`, `context_routing`. With exactly one selected document, repeatable
`--clause <clause-id>` restricts the update further. Unselected clauses and dimensions already
in the companion are retained. An unknown input cannot erase known knowledge; omission is not
an explicit empty set or a negative result. Existing protected values are reported as `protected`.
There is deliberately no blind overwrite/force flag and no automatic deletion of old assertions.

Use `--root /path/to/project` when invoking outside the checkout. All relative manifest, workspace,
evidence and report paths are resolved against that explicit root. Companion paths are fixed
relative to each manifest-declared AtlasData source, so parts and separately declared supplements
cannot be redirected by guessing a filename suffix.

## Public values versus private evidence

Public categorical fields include statement, knowledge and process functions and their primary
labels, Applicability presence/functions, role presence and controlled role types. Presence-only
and explicit negatives are supported. Vote counts describe support, not measured correctness.

Subject and routing models also contain protected evidence or free-text conditions. Their public
records therefore contain a **bounded projection plus a content-addressed value reference**.
The public subject view carries the selected normalized label, confidence and ambiguity labels;
the routing view carries source/target coordinates, reach/role and counts of conditions,
exclusions and qualifications. It does not copy those sentences. Exact accepted role tuples
travel privately; their public view contains only the tuple count. No extra role candidates are
accepted merely because they occur in an evaluation report.

Original context objects and redacted raw provenance are stored as immutable, hash-checked JSON:

```text
.atlas/data/knowledge-evidence/<sha256>.json
```

This is **private persistent evidence**, not a disposable cache and not a second canonical
repository. Keep it with the local source material; do not commit it into public AtlasData.
Protected clause text, evidence quotations, subject evidence text, reference titles, raw role
actors/targets and scope-condition prose are not copied into public companions. Free-text
provenance is replaced by hash references. Normalized subject labels and structural reference
coordinates are intentionally published as semantic values, and should be reviewed as such.

## Restore, including into a fresh workspace

```bash
uv run standards-atlas atlasdata import-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/data \
  --output local/review/atlasdata-knowledge-import-preview.json
```

Omitting selectors restores physical documents with an existing companion. Explicit selections
must have their corresponding companion; a missing selected file is an error. Existing canonical
content, baseline and unselected clauses remain in place. Missing canonical documents are built
as physical skeletons through the existing AtlasData importer/part selector, never as persisted
family composites.

```bash
uv run standards-atlas atlasdata import-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/data \
  --output local/review/atlasdata-knowledge-import-applied.json \
  --write
```

For a clean roundtrip test without touching the working documents:

```bash
uv run standards-atlas atlasdata import-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/work/atlasdata-roundtrip \
  --evidence-root .atlas/data/knowledge-evidence \
  --strict-evidence \
  --output local/review/atlasdata-knowledge-roundtrip.json \
  --write
```

With the referenced private evidence, accepted context objects and raw derivation metadata are
restored exactly. Without it, categorical values and public provenance/hash references remain
usable; contextual attributes requiring missing private values are reported as **`deferred`**.
They do not acquire invented empty conditions or known-false defaults, and an existing local
context is not erased. `evidence_unavailable` means only raw provenance could not be hydrated;
the public value is still available. `--strict-evidence` makes either case a preflight error.
Rerunning with the evidence store present hydrates the deferred values without a model call.

A fresh public import does not recreate copyrighted clause content. It reports
`Content not verifiable` until suitable local content exists. Already populated local text is
checked against the stored exact SHA-256 before any write.

## Identity and repeatability

Each companion binds the manifest's physical key, family, explicitly supplied publication year,
part selection and a structural fingerprint. Clause IDs and complete references, including the
AtlasData edition, are checked. The manifest edition and the legacy AtlasData reference year are
kept separate rather than silently correcting one from the other. An omitted supplement year is
not inferred from its parent.

AtlasData and local normalization may legitimately have different headings. Two hashes record
these two sources separately. Export checks the public structural heading against AtlasData;
existing enriched source content is checked against its enrichment heading and content hash.
A fresh text-free skeleton can use the recorded AtlasData heading. No heading is rewritten,
normalized again or published from private source text. Re-export retains the original source
fingerprint when only a structural skeleton is present.

All selected documents, identities, public schemas, known evidence hashes and conflicts are
validated before the first write. Public and private files are each replaced atomically;
canonical saves use the existing repository. This is **not a multi-file transaction**, and there
is no concurrent-writer lock. Do not run overlapping writers. Immutable private payloads are
written before public references; a later operating-system failure may leave harmless unreferenced
private blobs or a partially completed multi-document batch. Stable ordering and absence of
run timestamps make an identical replay byte-stable and avoid unnecessary rewrites.

Structure or source changes require deliberate reconciliation/review; these commands do not
silently remap stale knowledge. Reports cannot overwrite the manifest, public AtlasData,
canonical document files or private evidence.

## Tests

```bash
uv run pytest -q tests/integration/atlasdata/test_knowledge_roundtrip.py
STANDARDS_ATLAS_RUN074_ARCHIVE=local/evaluation/qualification-run-074.zip \
  uv run pytest -q -s tests/integration/knowledge/test_atlasdata_run074.py
```

The opt-in test combines actual AtlasData physical identities from this checkout with local
archive-matched source evidence in an isolated workspace. It verifies 497 accepted cases,
45 positive/452 negative Applicability decisions, 26 physical companions, untouched unqualified
cases and byte-stable export/import replay. It is not a fresh qualification or a verification of
the user's production workspace. The repository contains no protected standard-text fixture.

## Effective CBox and workflow reuse

[Canonical CBox](canonical-cbox.md) describes inspection of the accepted state, qualification
isolation and explicit workflow adoption/restore/publication. A normal `document import` or
default qualification workflow still does not implicitly load or publish companions.
Use `--restore-enrichments` for opt-in workflow restoration or the standalone command above.
Process-function qualification reporting remains separate; existing values are persistable.
