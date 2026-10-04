# AP03 Series H runbook — S15/S16 isolated Holdout and completion

Series H is the one-way transition from a confirmed pre-Holdout freeze to an AP03 release decision.
It is not another optimization phase. The commands below cannot make the supplied 2026-10-04 snapshot
ready by themselves: its Series-G handover still reports missing real Development/verifier/repetition
and H3 evidence. Stop at the first blocker and preserve that status.

## 1. Preconditions and ownership

Before any Holdout source or result is exposed, all of the following must already exist and be fixed:

- a confirmed Holdout Golden suite with `partition=holdout`;
- the bound reference-corpus partition/exposure plan with every selected Holdout case marked
  independent/eligible and no exposure blocker;
- project-owned G0-G6 thresholds/support requirements in a `SeriesHGateProfile`;
- the exact authorized Holdout experiment manifests for the Finalist and any baseline/repetitions that
  were approved in advance;
- the Series-G verifier/repetition evidence and G4/G5 profile;
- a Series-G freeze that binds the exact Series-H campaign hash and the current code revision;
- genuine H3 confirmation and a blocker-free `assertion-series-g-readiness` result.

The optimizer/Codex Development profile must not be given the Holdout suite, expected content, reports
or private Holdout workspace. Series-H execution does not need that client and never invokes it.

## 2. Fix the Series-H gate profile before Holdout

Create the versioned gate-profile JSON using the `ap03-series-h-gate-profile` schema. Required values
are deliberately not defaulted. The project owner must set at least the minimum Holdout cases and
independent source groups, maximum failed/not-executed/cached cells, mandatory engineering metric
thresholds/supports, critical diagnostic codes and maximum critical findings per repetition.

Do not copy numbers from a Holdout result. A changed gate profile has a different hash and invalidates
the frozen campaign binding.

## 3. Plan the exact Holdout experiments with the existing bounded runner

Use the existing `assertion-experiment-plan` command for the confirmed Holdout suite and approved
runtime/model route. Each manifest must be explicitly execution-authorized and must use fresh
repetitions/cache bypass. The manifest remains the existing experiment contract; Series H does not add
a second runner.

Prepare every baseline cell that is intended to appear in the final Holdout comparison **before** the
campaign is frozen. Do not add a baseline after seeing Finalist results.

## 4. Freeze the Series-H campaign identity

After the exact experiment manifests exist, prepare the immutable run order without model calls:

```bash
uv run standards-atlas evaluation assertion-series-h-campaign-prepare \
  --suite <confirmed-holdout-suite.yaml> \
  --partition-plan <partition-and-exposure.json> \
  --gate-profile <series-h-gates.json> \
  --campaign-id <campaign-id> \
  --finalist-experiment <finalist-experiment-id> \
  --baseline-experiment <optional-preplanned-baseline-id> \
  --workspace .atlas \
  --project-root .
```

Repeat `--baseline-experiment` only for cells that were part of the approved protocol. Record the
printed campaign SHA-256 in the Series-G freeze together with the current code revision and all other
S14 freeze identities. Then obtain genuine H3 confirmation and regenerate
`assertion-series-g-readiness`. Do not edit the campaign, gate profile or manifests after this point.

## 5. Model-free preflight

```bash
uv run standards-atlas evaluation assertion-series-h-preflight \
  --readiness <series-g-readiness.json> \
  --campaign <series-h-campaign.json> \
  --gate-profile <series-h-gates.json> \
  --suite <confirmed-holdout-suite.yaml> \
  --partition-plan <partition-and-exposure.json> \
  --workspace .atlas \
  --project-root .
```

The preflight performs zero model calls. `ready_to_execute=false` is a hard stop. Typical blockers are
a non-ready Series-G decision, mismatched freeze/campaign/gate/partition hashes, a non-Holdout suite,
exposed source groups, changed/unauthorized experiment manifests, altered repetition counts or a code
revision different from the freeze.

## 6. Execute exactly the frozen Holdout campaign

Only after a blocker-free preflight:

```bash
uv run standards-atlas evaluation assertion-series-h-run \
  --readiness <series-g-readiness.json> \
  --campaign <series-h-campaign.json> \
  --gate-profile <series-h-gates.json> \
  --suite <confirmed-holdout-suite.yaml> \
  --partition-plan <partition-and-exposure.json> \
  --config cfg/llm.yaml \
  --workspace .atlas \
  --project-root .
```

This command runs the already frozen experiment IDs in their frozen order through the existing bounded
runner. It has no adaptive variant selector and no optimizer-client call. A transport/model failure is
kept as experiment evidence; it is not a reason to substitute a new prompt, model or threshold.

## 7. Evaluate and close AP03

First finalize without inventing a human release decision:

```bash
uv run standards-atlas evaluation assertion-series-h-finalize \
  --readiness <series-g-readiness.json> \
  --campaign <series-h-campaign.json> \
  --gate-profile <series-h-gates.json> \
  --suite <confirmed-holdout-suite.yaml> \
  --partition-plan <partition-and-exposure.json> \
  --workspace .atlas \
  --project-root .
```

The finalizer uses the existing `AssertionQualificationEvaluator` and all planned repetitions. It
writes `series-h-completion.json`, `series-h-quality-report.md`, the individual bound Holdout reports
and `ap04-handover.md`. Missing attempts/repetitions, technical failures, cache use beyond the fixed
policy, insufficient support and critical findings remain visible. A negative result is
`evaluated_not_qualified`; do not rerun the same Holdout with a tuned configuration.

If and only if the frozen Holdout passes, the project owner may record the separate release decision:

```bash
uv run standards-atlas evaluation assertion-series-h-finalize \
  <same frozen inputs as above> \
  --release-decision approve_bounded_pilot \
  --release-reference <human-decision-reference> \
  --qualification-scope "<explicit bounded pilot scope>"
```

A `do_not_approve` decision is also valid and remains non-release. The release reference records a
human decision; the CLI does not authenticate or fabricate the person. Canonical knowledge adoption is
disabled in all Series-H outcomes.

## 8. Interpreting completion states

`implemented_not_evaluated` means the software path is available but no Holdout evidence has been
assessed. `blocked_by_missing_evidence` means required preflight or campaign evidence is absent or
invalid. `evaluated_not_qualified` means a real campaign was evaluated but either gates failed or the
human bounded-release decision is absent/negative. `qualified_for_bounded_pilot` requires a passed
frozen Holdout plus explicit human approval and a non-empty scope; it is not a general production or
formal tool-qualification claim.

## 9. Current supplied snapshot

For `standards-atlas-current-202610041845.zip`, stop before Holdout preparation/execution until the
missing Series-G evidence described in `docs/development/ap03-status.md` is restored and genuinely
confirmed. The Series-H implementation and public synthetic E2E test do not turn those missing private
proofs into passed evidence.
