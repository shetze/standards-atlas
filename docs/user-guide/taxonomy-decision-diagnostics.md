# Inspect taxonomy decision plans

Slice 2 of the taxonomy-grounded Efficient cascade adds **read-only diagnostics**.
It does not activate new structural acceptance rules, request a model, change the
Applicability policy, or publish semantic enrichments. It measures the available
source evidence before the later inference and cascade changes are enabled.

## Diagnose an existing qualification run

```bash
uv run standards-atlas evaluation taxonomy-decisions \
  --run local/evaluation/qualification-run-078.zip \
  --output local/evaluation/taxonomy-efficient/slice-2/run-078
```

`--run` accepts a qualification ZIP or a run directory containing the immutable
selection and its dataset/corpus snapshots. The selected clauses and available
archive checksums are verified. The complete selection is accounted for, including
clauses without any model consensus. Original artifacts are never overwritten.

The output must be a **new, separate directory** outside the source run. A malformed
selection, changed content hash, unsupported source schema or conflicting source
identity is an input error. It must not be reported as a negative semantic decision.

A newly built corpus may be inspected before any model run using `--dataset`
instead of `--run`. Pass the path of its `dataset.json`. This alternative diagnoses
all examples in that dataset; it does not claim to reproduce a historical run's
selection. Provide exactly one input option. Dataset targets, tags and expected
labels are not used by the rules.

## Output artifacts

| Artifact | Purpose |
|---|---|
| `taxonomy-decision-plans.json` | One versioned `ClauseDecisionPlan` per selected clause, with source facts, authority and rule evidence. |
| `taxonomy-decision-report.json` | Counts by attribute, rule, document and document family; fingerprints and comparison against the frozen legacy structural prior. |
| `taxonomy-decision-report.md` | Human-readable summary and limitations. |
| `taxonomy-decision-review.csv` | Pending review rows with clause/reference coordinates, candidates, rules and source/plan hashes. |
| `rules.yaml` | Exact packaged rule resource used by the diagnostic. |
| `review.yaml` | Pending synthetic reference cases for independent review; not published semantic gold. |

`fixed_primary_would_change` compares a fixed diagnostic primary to the old
structural rule result. `legacy_primary_not_fixed_by_plan` also includes old values
that the new plan can only support as hints. Neither counter is a changed production
output, a measurement of accuracy, or an early-exit count.

## Interpret the four states

| State | Meaning in this slice |
|---|---|
| `fixed` | A rule permits this specific predecision and its required source facts are explicitly confirmed. This is still only diagnostic. |
| `hint` | There is relevant structural evidence, but authority, rule qualification or semantic specificity is insufficient for a binding decision. |
| `open` | No rule assessed this attribute. This is neither false nor an evaluated empty set. |
| `conflict` | Direct structural observations disagree; no winning semantic value is selected. |

The first rule profile allows a confirmed term entry to fix only
`primary_function=definition`. It **does not** fix `knowledge_kinds`, the complete
`statement_functions` set, roles or Applicability. A definition may define a
process, a role or a technique.

Requirement markings remain hints because they need prohibition/recommendation
and mixed-statement granularity. Objective, heading and technique-catalogue rules
also remain `hint` until independently reviewed. `Requirements on objectives` is
not treated as a pure Objective. An `objective` source marker in a local or immediate
`Work products` section is a conflict. General ancestor headings do not override a
more specific confirmed local type.

A technique-entry hint requires catalogue context, a leaf boundary, and valid,
nonoverlapping `Aim:`/`Description:` offsets in the actual clause text. Those two
labels without the catalogue/boundary only produce a weaker segment hint. The
technique's aim does not make the whole entry an Objective. Notes stay in the text
and content hash.

**Applicability stays open for every clause type.** Technique usability is not
normative applicability, but an embedded note may state where requirements do or
do not apply. This diagnostic cannot safely decide that question from type alone.
It introduces no public Usability field and no `applicability_functions` output.

## Source authority and reproducibility

The clause provider now adds an independent `source_structure` contract to current
canonical CBoxes and newly generated corpora. It records baseline field paths,
clause/reference coordinates, actual ancestor distance, structural taxonomy names
and versions where present, source authority/generator and evidence, and content
identity. Missing provenance is `unattributed`, not confirmed.

Only source/baseline paths are allowed. LLM/imported interpretations under baseline
are excluded unless separately confirmed as source structure. Unknown generated
facts remain unavailable; an interpreted child cannot hide inside a parent
collection. Semantic enrichments, subject interpretations, routing interpretations,
semantic confirmations and golden targets cannot supply independent source facts.

Old archives lack this contract. The explicit legacy reader accepts `title` only
when the canonical `heading` key is absent, including for ancestors. It never writes
a second `title` field or manufactures authority. Consequently, many old findings
remain hints even where current source-attributed data could support a fixed
predecision. Do not edit an old archive to add retrospective confirmations.

Plans use stable JSON fingerprints and versioned rules. Identical source facts and
inputs produce reproducible plans; changed text or provenance changes identity.
A future rule promotion needs a separately reviewed/versioned profile, not changing
`maximum_state` of an unreviewed rule to `fixed` in place. The supplied review cases
are pending contract examples, not proof of empirical precision. Review original
structure and rule applicability independently; model majorities are not gold.
Editing the CSV does not automatically import or activate anything.

## Deliberate production boundary

Production consensus explicitly remains pinned to **`legacy-v1`**, preserving the
old rule behavior for the B0 baseline. Its historical `title` handling is not
silently replaced with newly activated heading rules. Correct `heading` handling
and the new conservative rules are evaluated by the diagnostic plan. The shared
`taxonomy_structural_evidence(plan)` projection is the single new rule view for
pre-inference and future post-inference consumers; it contains no numeric confidence
or synthetic votes.

Existing prompt frames ignore the new source contract. Their visible inputs and
qualification input fingerprints are unchanged. Rebuilding a corpus adds metadata
and therefore changes that **corpus artifact's** checksum; preserve old immutable
selections rather than replacing their snapshots.

No EngineeringDocument or public enrichment schema change is needed. Source,
decision-plan, report and packaged rule/review interfaces are registered with the
central schema inventory. Slice 1 routing fixes and the presence-only Applicability
export remain unchanged. Actual request reduction and acceptance/early-exit changes
belong to later slices and require separate quality measurements.
