# AP03 Series G runbook — S13/S14

Series G is Development-only. It measures the verifier, closes cascade end states, executes only
pre-authorized fresh repetitions, and freezes the candidate/gates before Holdout. It does not change
Golden expected content, access Holdout, publish canonical knowledge or claim qualification.

## 1. Verifier benchmark

Prepare a JSON array of `VerifierCaseObservation` objects from actually annotated Development truth.
Each case declares `kind=real_annotated` or `synthetic_mutation`, the expected candidate disposition,
missing-item truth and a stable annotation reference. The observation contains the actual
`AssertionClauseVerification` returned by the verifier.

```bash
uv run standards-atlas evaluation assertion-series-g-verifier-evaluate \
  --observations local/evaluation/assertions/ap03/<campaign>/verifier-observations.json \
  --output local/evaluation/assertions/ap03/<campaign>/verifier-metrics.json
```

Synthetic mutations are useful for deterministic known-error probes but do not qualify a real
verifier. Keep real and synthetic supports visible.

## 2. Optional bounded second-verifier factor

The default cascade leaves escalation output unverified:

```bash
uv run standards-atlas evaluation assertion-cascade ... \
  --leave-escalation-unverified
```

To measure exactly one extra verifier pass as a separate factor:

```bash
uv run standards-atlas evaluation assertion-cascade ... \
  --verify-escalation
```

An escalated clause is `technically_verified` only if this second pass completely reviews the
escalation candidates, detects no missing items and the escalation itself has no extraction failure or
violation. Otherwise it remains `needs_review` or `failed`. The extra calls must be included in the
approved budget comparison.

## 3. Fresh repetitions

Use the existing `assertion-experiment-plan`/`run`/`resume`/`report` path for the approved Finalist and
required comparison configuration. Set the pre-agreed repetition count before execution. Repetition is
a new inference attempt, not cache replay; `bypass_cache_for_repetitions` must remain true. Keep each
run/report separately and bind its hash. Never select a best attempt.

Materialize `RepetitionEvidence` with planned/completed/fresh/cached counts, all bound report hashes
and unstable case IDs. A cached result is not independent stability evidence.

## 4. Pre-Holdout gate profile and freeze

`SeriesGGateProfile` requires explicit G4/G5 values before Holdout: maximum verifier false-acceptance
and false-rejection rates, minimum missing-item recall, minimum verifier coverage, minimum real
annotated cases/candidate support and required fresh repetitions. Unset values are blockers. Human H3
confirmation requires a real reference; it is never synthesized by the CLI.

`SeriesGFreeze` binds code, prompt bundle, task schema, ontology fingerprint, source/context policy,
model/backend, cascade policy, retry/budget policy, Development Golden, partition/exposure state,
evaluator and the concrete future Holdout campaign. Canonical adoption is fixed off.

Then evaluate readiness:

```bash
uv run standards-atlas evaluation assertion-series-g-readiness \
  --metrics local/evaluation/assertions/ap03/<campaign>/verifier-metrics.json \
  --repetitions local/evaluation/assertions/ap03/<campaign>/repetitions.json \
  --gate-profile local/evaluation/assertions/ap03/<campaign>/gate-profile.json \
  --freeze local/evaluation/assertions/ap03/<campaign>/freeze.json \
  --output local/evaluation/assertions/ap03/<campaign>/series-g-readiness.json
```

A blocker-free result means only that the pre-Holdout prerequisites are bound. Series G always forbids
a qualification claim. Series H performs the isolated Holdout and final bounded release decision.
