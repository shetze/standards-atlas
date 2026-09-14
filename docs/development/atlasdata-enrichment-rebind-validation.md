# AtlasData enrichment structural rebind validation

Date: 2026-09-14

## Scope

The rebind repairs only the structural binding made stale by the reviewed multipart normalization
change that replaced synthetic clause-0 headings (`Part N`) with the canonical AtlasData clause-0
title. It does not migrate schema versions or reinterpret enrichment values.

For each selected companion with a stale structure hash, preflight requires:

- unchanged document/family/part/publication-year identity;
- exactly one current part root clause (`reference.clause == "0"`);
- an exact reconstruction of the stored structure hash when only that current root heading is
  changed back to the historical `Part N` value;
- unchanged AtlasData TOC MD5 foreign keys and references for every published clause record;
- unchanged structural headings for every non-root published clause record; and
- a root record, when present, that is itself bound to the historical `Part N` heading.

Only after every selected document passes preflight may `--write` replace companions. The rebind
updates the document-level structure fingerprint and, if the root has a published record, its
heading and heading fingerprints. Attributes, origins, generated/confirmed provenance, evidence
references, private-value references and content fingerprints are retained.

## Automated checks

- `tests/integration/atlasdata/test_enrichment_rebind.py`: 5 passed.
- `tests/integration/atlasdata/test_knowledge_roundtrip.py` plus schema guards and the new tests:
  447 passed.
- `tests/architecture`: 140 passed.
- Python compilation of the changed source files passed.
- A dry run against the actual snapshot accepted `EN50126-1`, `EN50126-2`, and `ISO26262-11` as
  exact historical `Part N` projections. The observed ISO 26262-11 transition is
  `Part 11` -> `Guidelines on application of ISO 26262 to semiconductors`.

A single all-family dry run was not completed inside the execution time available here because the
large ISO 26262 / IEC 61508 AtlasData and sidecars take longer to parse. Validation covers the complete selected set before the first write: if any remaining companion has
structural drift beyond the accepted root-title change, no selected companion is written. Each
subsequent file replacement is atomic, matching the existing AtlasData transfer boundary.

Ruff was not available in the execution environment. Changed Python files were checked for lines
longer than 100 characters and compiled successfully.
