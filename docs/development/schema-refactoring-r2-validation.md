# Schema refactoring R2 — validation

## Scope and source

Input: `standards-atlas-current-202609140542.zip` (Git archive comment:
`3db8ce4f66d7ffa1a116d7ed54d4924b834f3b85`). The input contains both the integrated
R1 current-only guards and the complete Slice-4 Handoff. Neither is replaced by an
older snapshot. Input ZIP SHA-256:
`766ad72f3450d093e51291e3e512d702c06626c7dec89dcf425432c2b0b97e67`.

This change is confined to the three R2 schema families:

- `partial-qualification-manifest`: current/readable 1.1 only;
- `partial-review-publication`: current/readable 1.1 only;
- `partial-qualification-campaign`: current/readable 2.0 only.

AST comparison of the central registry confirms that all other 54 family policies,
including R1 and the archive/Handoff envelopes, are unchanged. There is no global
schema-policy change, dependency update, migration utility, production annotation,
model/prompt change, threshold relaxation or activation.

## Contract and boundary checks

The new R2 test module contains 104 synthetic cases. It covers mandatory version markers,
wrong/missing/obsolete markers through mappings, JSON, nested manifests and unchecked model
copies; writer/registry mismatch; all three evidence modes; an Atlas publication mixed
with independent external Development; obsolete embedded Handoff manifests; immutable
current publication fingerprints; mandatory Workbench evidence; rehashed kind/inventory
changes; missing or extra physical evidence; input symlinks; failed replay/resume without
mutation; and existing release gates on unevaluated campaigns.

The existing Legacy-publication success test is now an obsolete-format rejection test.
The previous campaign downgrade test also rejects 1.2. Existing tests for source drift,
annotation rules, Holdout separation, incomplete human decisions, Web confirmation,
MCP restrictions, archive/exposure replay and release authority remain in the regression.

The first existing-test run had one error-message mismatch: the new inventory guard rejected
missing evidence correctly, but its wording did not match the existing assertion. The
message was corrected; the existing assertion was not weakened.

## Executed checks

The full regression ran as `pytest -q`: **3,063 passed, 14 skipped, 4 warnings**.
The four warnings concern only `qualification-matrix-manifest` 1.5, left for R3;
there are no R1/R2 schema warnings. The skipped paths require optional dependencies,
private fixtures or explicitly enabled browser checks.

The full run collected the initial 95 R2 cases; nine further boundary cases were then
added. The final targeted command for the R2 module plus the unchanged existing missing-pair
regression passed **105 tests**, without warnings. This is 104 new R2 cases plus one
existing test, not additional production qualification evidence.

The ZIP was applied to a freshly extracted copy of the input snapshot and the architecture,
schema, R1, complete R2, Handoff and review-package modules were rerun there:
**340 passed, no skips or warnings**. The final documentation-only edits were then repackaged;
all delivered Python/test files were verified byte-identical to this tested clean tree.
Test groups overlap and must not be added.

```bash
pytest -q tests/architecture tests/unit/application/schema \
  tests/unit/application/semantic_qualification/test_partial_schema_refactoring.py \
  tests/unit/application/semantic_qualification/test_review_schema_refactoring.py \
  tests/unit/application/semantic_qualification/test_review_handoff.py \
  tests/unit/application/semantic_qualification/test_review_package.py
```

## Delivery checks

The changes ZIP contains **23 new/modified files**, relative to the project root, with no
deletions. It does not include a full project copy, productive corpus data, generated
reviews, environment files or test outputs. Reapplication preserves **all 1,490 unchanged
input files byte-for-byte**. Each delivered file was compared to the working implementation;
ZIP CRC/integrity, Python compilation, changed-file line lengths/import usage, local Markdown
links and whitespace checks passed. The supplied source manifest uses 1.1; R1 policies and
all unrelated schema families remain unchanged.

The two direct input modes and the archived Handoff are tested as current functionality,
not retained legacy artifact versions. Old frozen campaigns cannot be upgraded by rewriting
only their version field, dropping evidence, changing its kind or recomputing one hash.
No default warning filter was weakened. No production behavior is claimed on the strength
of the synthetic model or reviewer identities in these tests.

## Current-publication identity check

Using the unmodified input snapshot in an isolated process, a synthetic current publication
1.1 was created with the original code. The R2 code then loaded and replayed that exact
publication, verified both derived suites and reproduced the original `evidence_sha256`
without changing a byte in the file. This checks continuity of the **current** 1.1 contract;
it is not a legacy-publication reader or a test using real human review data.

## Environment limitations

Python 3.13.5 was used. Ruff is not installed; an explicit installation attempt failed
because the environment could not resolve `pypi.org`. Python compilation, a changed-file
line-length/import-use check, `git diff --check`, local documentation links and ZIP byte
comparisons are checked separately; they are not represented as a Ruff run.

Tests use synthetic corpora and simulated gateways. No production LLM run, real Codex/MCP
session, live human annotation or production qualification/activation was performed.
Browser/live optional transports are not newly tested by this schema-only change; existing
in-process Web and MCP service regressions run where the optional dependencies are present.
