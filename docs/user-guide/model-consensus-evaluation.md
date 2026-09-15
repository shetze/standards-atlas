# Model-consensus evaluation

Model consensus is a proposal mechanism for applicability qualification. It is not an independent source of truth and it does not publish clause-classification labels.

Run the configured qualification matrix first:

```bash
uv run standards-atlas evaluation qualification-matrix \
  --manifest manifests/applicability-presence-qualification-v1.yaml \
  --output .atlas/data/evaluation/qualification
```

Repeated predictions are collapsed per model before votes are compared across models. Reports distinguish unanimous agreement, strong or majority consensus, disputes and insufficient evidence. The accepted result is still subject to the configured qualification and review policy before canonical adoption.

Reviewers must consider proposal anchoring: a plausible automated proposal can survive simply because interpreting difficult clauses is expensive. Therefore:

- preserve the original clause and structural evidence;
- expose disagreement and insufficient-evidence cases prominently;
- keep generated proposals separate from reviewer decisions;
- treat Applicability Presence and polarity as explicit, separately reviewable claims;
- permit an unresolved result rather than inventing a semantic classification.

## Context and applicability

Corpus entries carry source and structural context used to interpret the clause. Structural Scope membership and explicit applicability semantics remain separate concepts:

- structural context records where the clause occurs in the document;
- `ClauseApplicability.present` records whether the clause explicitly expresses applicability semantics;
- optional polarity records `included` or `excluded` only when that distinction is supported.

Already accepted applicability is excluded from source-only qualification inputs so a successful enrichment does not feed back into its own next qualification run. Downstream CBox consumers may still use the accepted applicability result.

The retired statement-function, knowledge-kind, process-function and role-classification dimensions are not part of the current consensus contract. Engineering meaning beyond context and applicability is represented by evidence-backed entities and normative assertions.
