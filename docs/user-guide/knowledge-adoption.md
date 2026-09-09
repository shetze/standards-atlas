# Accepting qualified knowledge into canonical documents

This first persistence slice uses the existing `EngineeringDocument` repository. It accepts
selected run results as **generated knowledge**, not as authoritative confirmations, and
never calls a model. It does not yet export generated attributes into public AtlasData.

## Prerequisites

Use an immutable qualification ZIP (or its extracted archive with `archive-manifest.json`)
containing the final consensus, run-local corpus/dataset/coverage and completed Applicability
policy reports, such as `qualification-run-074.zip`. A mutable run work directory is not
accepted in this slice. Required member hashes, sizes and selection fingerprints are checked.

Target physical documents must already exist under `.atlas/data/documents`. Their document
key, clause ID, reference, heading and exact text hash must match the archived selection.
Run 074 carries short clause references, not a separately verifiable edition identifier.
No additional edition check is claimed beyond the available keys, references and fingerprints.
Missing documents or stale clauses cause an error before any document is written; the
archive is never used to manufacture replacement source documents. A family is not stored
as a synthetic canonical document. Use `--document` to target existing physical parts.

## Preview, then write

```bash
uv run standards-atlas document adopt-qualification \
  --run local/evaluation/qualification-run-074.zip \
  --workspace .atlas/data \
  --output local/review/knowledge-adoption-074-preview.json
```

Omitting `--write` is a dry run. The optional output is a local JSON change report. Check
`protected`, `unknown`, `not_evaluated` and the addressed document/clause counts before writing.

```bash
uv run standards-atlas document adopt-qualification \
  --run local/evaluation/qualification-run-074.zip \
  --workspace .atlas/data \
  --output local/review/knowledge-adoption-074-applied.json \
  --write
```

`--document ISO26262-11` restricts the operation to a physical document; the option is
repeatable. `--dimension` is also repeatable and accepts `statement_functions`,
`knowledge_kinds`, `applicability` and `role_semantics`. Without it, all four are addressed.
This version still requires a complete policy archive even for a subset of dimensions.

The entire target set is validated first. Each changed document is replaced atomically;
this is **not a multi-file transaction** in case of an operating-system failure during saves.
There is no multi-process writer lock; do not run overlapping canonical writers concurrently.
A repeat with identical input/state does not rewrite documents. Unselected clauses, baseline
content, existing subject/routing enrichments and independently confirmed values are retained.
Run snapshots are read-only. Report destinations cannot overwrite input archives or canonical
document files. Reports may describe existing semantic values and belong in ignored local data.

## Source and acceptance policy

`canonical-knowledge-adoption-v1` selects attributes, not globally resolved clauses:

| Attribute | Source and treatment |
|---|---|
| Statement functions and explicit primary | Final cascade selection, with stage-specific primary support and cumulative set support. |
| Knowledge kinds and explicit primary | Final cascade selection; insufficient decisions are recorded as unknown. |
| Applicability presence | Only `applicability-policy-run.json` `cases[].final_present`, never the pre-policy gate. |
| Role-semantics presence | Final presence decision; no automatically accepted exact role tuples. |
| Process functions | Not supplied by these archive votes; preserved and reported as not evaluated. |
| Applicability functions/polarity | No new detail inferred. Presence is usable without details; negative presence clears incompatible generated details. |
| Subject and routing context | Existing canonical enrichment remains untouched by adoption. |

A global `review_required` does not block independently usable results. The importer does not
re-vote, retune thresholds or relabel disputed final decisions as measured truth. Recorded
support includes the source artifact hash, stage, prompt/model identifiers and decision rule.
Each distinct model vote counts once; retries/repetitions are not independent voters. Primary
abstentions are separate from valid votes. Policy decisions have policy lineage, not invented
numerical vote support. Source-independent tuple extraction and full CBox framing are not
changed here.

The partial transfer contract retains omitted fields across JSON roundtrips. An explicit
`false` or an evaluated empty set is known; an unavailable decision is unknown. Unknown input
does not erase a previously known value. A schema default without an assessment is not
an inferred negative. Consumers must inspect provenance availability, not only boolean
defaults; full downstream CBox/workflow integration remains the subsequent slice.

## Authority and compatibility

Canonical documents now write schema **9**. Schema **8** is read with a deprecation warning;
loading alone does not rewrite it. Generated markers are retained. Populated unmarked v8
enrichments are protected as `unattributed_attributes`, because the old serialization cannot
prove whether they were imported from reviewed AtlasData or created without provenance.
Empty defaults remain unassessed. No default field is blanket-locked as authoritative.

An explicit domain confirmation, for example
`clause.confirm_authoritative("enrichments.semantic.applicability_present", authority="review")`,
records the authority and removes generated/unattributed metadata for that attribute. Both
semantic and context enrichment services respect these confirmations. There is no automatic
confirmation and no force-overwrite CLI in this slice. Resolve reported authority conflicts
through a reviewed update rather than deleting provenance to force a model result through.

The existing AtlasData importer now correctly reconstructs Applicability presence from
`AF-*` tags and records explicit confirmations for actually supplied tag dimensions.

## Incremental reviewed AtlasData annotations

The existing annotation writer is still the reviewed, text-free public path. It now accepts:

```bash
uv run standards-atlas atlasdata apply-semantic-annotations \
  data/ISO26262 reviewed-annotations.yaml --merge --write
```

`--merge` changes
only explicitly supplied annotation dimensions; an explicit empty list clears that dimension.
Statement primary/secondary tags form one atomic group. An omitted field leaves its namespace
unchanged. The semantic profile cannot be reinterpreted during merge. Without `--merge`, the
previous whole-annotation replacement behavior remains. Presence-only, generated provenance,
subject/routing and unassessed negatives are **not** newly encoded as public tags in this slice.

## Reproducible checks

```bash
uv run pytest
uv run ruff check .
STANDARDS_ATLAS_RUN074_ARCHIVE=local/evaluation/qualification-run-074.zip \
  uv run pytest -q -s tests/integration/knowledge/test_adoption_run074.py
```

The opt-in archive test builds isolated canonical targets from the archive's source identity,
then checks preview, write, reload and byte-stable replay. Expected for run 074: 497 addressed
clauses, 45 positive and 452 negative Applicability decisions, three unqualified clauses
untouched, 26 changed documents and zero replay writes. It is not a fresh LLM qualification
and not a test against the user's full production workspace. No standards text is embedded
in the repository's test fixtures.
