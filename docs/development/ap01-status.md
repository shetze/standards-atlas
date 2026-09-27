# AP01 status — Series C / S07–S08

Date: 2026-09-27. Series C implementation is complete in this delivery; user-local
`uv run ruff check .` and the uninterrupted full `uv run pytest` remain the acceptance
check after applying the delta. Series D is not implemented.

## Snapshot prerequisite recovered

The supplied Series-C snapshot has SHA-256
`868bd1576ea6c6160375e0a71271b4f99e8265c9cdacec9c0907f60082afeaa2`, which is exactly
the recorded base of the already delivered Series-B delta. Its Series-B files were still
at their recorded pre-Series-B hashes and `source_resolution.py` was absent. The working
tree therefore reapplies the previously delivered Series-B delta byte-for-byte before
adding S07-S08. Consequently this Series-C delta, which is correctly based on the supplied
snapshot, also contains those prerequisite Series-B changes. No new Series-B semantics
were invented during this recovery.

## Delivered boundaries

S07: the formal ontology subclass hierarchy is a shared deterministic component used by
both proposal unification and assertion evaluation. Work-product membership is derived
only from `WorkProduct` plus transitive `rdfs:subClassOf` declarations in the explicitly
bound ontology resources. `EngineeringRecord` and transitive classes such as
`VerificationPlan` qualify; `EngineeringArtifact` alone does not. The report now carries
`work_product_precision`, `work_product_recall`, `work_product_class_accuracy` and
`required_work_product_relation_recall`, plus exact ontology resource SHA-256 bindings.
A same-identity candidate typed only as `EngineeringEntity` remains in the WP class-
accuracy denominator. Literals, wrong relation direction/predicate and predicate-domain
inference do not manufacture a required WorkProduct relation.

S08: case reports now retain traceable diagnostic findings using the AP01 vocabulary.
Unique class, predicate and normative-force differences can be rule-based findings;
technical invalid grounding can be rule-based as well. Strictly missing/additional or
ambiguous semantic objects remain `needs_review`/`unclassified_semantic_mismatch` where
the difference alone does not prove the fachliche cause. Retained proposal violations can
suggest note/list/context/condition and related codes but never become human-confirmed
without an explicit human annotation. Additional assertions are not automatically marked
`invented_assertion`; heading evidence is not by itself `wrong_context_use`. Diagnostics
do not alter strict metrics.

Current evaluation contract remains `assertion-clause-local-v1`; schema families remain
at schema 1 under the clean-break policy. Golden expectations, audit bytes, productive
context selection and model/prompt behavior were not changed. No model, verifier, cascade,
embedding, unification merge or canonical adoption run is part of Series C.

## Actual checks in this delivery environment

The prerequisite Series-B evaluation/unification check passed 25 tests before Series-C
changes. After S07, the focused evaluation, work-product and unification gate passed 30
tests. After S08, the focused assertion evaluation/work-product/unification gate passed
36 tests before the broader Series-C checks recorded in `_delivery/tests.md`.

The environment uses the available Python 3.13 interpreter with `PYTHONPATH=src` for these
checks. `uv run --offline` cannot resolve the project environment because required wheels
are not fully present in the local uv cache; this remains an environment limitation, not
a substituted claim that the user's local Ruff/full-pytest acceptance has passed.

## Next authorized implementation boundary

After the user's local Ruff and full-pytest checks, Series D may implement S09-S10:
end-to-end/No-LLM hardening and the reproducible private v8 pilot baseline. Do not start
AP02/AP03 as part of a Series-C correction.
