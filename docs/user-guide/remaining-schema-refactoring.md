# Remaining schema refactoring R3

R3 removes concrete obsolete reader/writer paths from the remaining six families.
It does not run models, qualify clauses, confirm human decisions, migrate old evidence,
change thresholds, or implement the global R4 policy guards.

## Active contracts

| Family | Only supported version | Change |
| --- | --- | --- |
| Cascade provenance | 1.6 | Explicit marker checked by writer and all consuming projections/replays. |
| Qualification matrix report | 1.1 | Explicit model marker, writer guard and archive/Challenger readers. |
| Qualification consensus | 5.0 | Required marker; no schema-4 serializer or fingerprint preservation. |
| EngineeringDocument envelope | 1 (integer) | Clean-break reset; no reader or migration for older envelopes. |
| Knowledge adoption batch | 1.1 | Required marker; explicit source requirements, including empty lists. |
| Qualification matrix manifest | 1.6 | Required marker at model/YAML/workflow/archive entry points. |

The four shipped v3/v4/v5 matrix files change **only** their serialization marker from
1.5 to 1.6. Their IDs, prompt/model/resource versions, selection rules and thresholds stay
unchanged. Filename `v3`, `v4` or `v5` is not a serialization-schema selector.

R1, R2, review archives, Handoff, public AtlasData formats and the golden-proposal schema
are unchanged. In particular, a golden proposal using schema 4.0 is not an obsolete
ConsensusReport 4.0. Schema families have separate axes.

## Existing artifacts

Keep historical files unchanged. Do not replace version strings, recompute old hashes or
reuse old execution identities as a migration. Obsolete request/report/campaign inputs must
be regenerated into **new output directories** from current source/configuration contracts.
A current valid artifact remains readable; its age alone is not a rejection criterion.

Pre-reset EngineeringDocument files are not upgraded or skipped in inventories; `.atlas` is regenerated under schema 1.
Back up and relocate obsolete files outside the active repository. Rebuild derived documents
through the current source workflow. Do not discard human-reviewed information: preserve
its original evidence for an explicit source-bound review/transfer. There is no automatic
migration or source-free authority inference in this slice. Normal schema-9 reads never
rewrite canonical files and preserve generated, confirmed and unattributed provenance.

Current Consensus 5.0 serialization is retained. Adoption batches now always serialize empty
`source_requirements` as `[]`; there is no compatibility fingerprint for the previous omitted
representation. Source-archive hashes still identify the original evidence, not the batch.
An old original Run 074 archive is rejected; it is not an alternative production reader.

## Qualification and historical review

The same model contracts validate direct loads, manifest catalogs, campaign matrix snapshots,
Challenger selection, extraction eligibility/provenance, replay and adoption. Archive readers
verify checksums **and** the recognized embedded contracts they consume. The analysis archive
writer validates recognized members before creating a ZIP/index and rejects conflicting names.
Opaque unrelated files are not claimed to have been semantically validated.

History failure reports identify the input/member and prevent publication of a new candidate
index. They do not change Development/Holdout membership, turn missing history into a clean
independence claim or infer annotations. Model votes are inspected using the original raw keys:
absent is unobserved, explicit `false` is negative, explicit `null`/empty is not absence.
Challenger comparison likewise ignores a missing Presence vote rather than treating it as false.

Context/corpus workflow checkpoints also validate the document envelope before comparing
input hashes. A stale checkpoint is not a way to reuse an obsolete canonical document.

R3 does not change process support, applicability policy, acquisition of human confirmation,
review disclosure, release/activation gates, or measured/unmeasured timing semantics.

## Local checks

```bash
uv run pytest tests/unit/application/semantic_qualification/test_schema_refactoring_r3.py
uv run pytest tests/unit/adapters/filesystem/test_document_repository_schema.py \
  tests/unit/adapters/mcp/test_formula_transcription.py
uv run pytest
```

The focused R3 suite uses only synthetic sources; its schema warnings are test errors.
Private original Run 074 tests remain opt-in via `STANDARDS_ATLAS_RUN074_ARCHIVE`, but now
verify rejection without archive mutation or canonical/public writes. Positive current-format
adoption/AtlasData/CBox roundtrips use reproducible synthetic qualification evidence.
