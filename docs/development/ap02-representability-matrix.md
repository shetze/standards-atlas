# AP02 Series F representability matrix

Date: 2026-10-02.

This matrix records what the completed AP02 source/context/evidence contracts can **represent and
check deterministically**. It is not a model-quality result, a new Golden annotation set, or an AP03
holdout. The confirmed patterns below are taken from the existing fachlicher Leitfaden; the tests use
public synthetic inputs unless they are existing AP01 offline contract tests.

## Confirmed review patterns and their AP02 representation

| Confirmed pattern | AP02 representation now available | Reference cases / tests | Qualification boundary |
|---|---|---|---|
| Heading definition | Heading and body are distinct source surfaces with explicit origin and real source ownership. Heading evidence can ground an entity without pretending that the heading belongs to the local body. | T01-T03, T19; `test_common_grounding_core_supports_heading_body_and_foreign_context` | Proves source/evidence representation, not whether a model recognizes the right term. |
| Safety-plan structural context | Textless parent headings, preceding introductions, target detail clauses and later contextual clauses remain distinct candidates with structural paths and bounded selection reasons. | T04-T09, T19, T25-T26; Series-F end-to-end test | Candidate availability and technical grounding do not by themselves confirm semantic reach. |
| HFT multi-span evidence | One assertion can retain two or more exact spans, including an introduction and a list item, with separate offsets and use contributions. | T16-T22; `test_intro_and_list_item_remain_two_distinct_evidence_spans` | No mounted quote is created; semantic adequacy remains unassessed. |
| Separate required work products | The productive proposal contract supports multiple independently grounded entities plus assertions whose endpoint identity is kept separate from evidence identity. | T19, T31; Series-F end-to-end test plus existing projection/roundtrip tests | The synthetic test demonstrates transport and resolution, not correct extraction of real work products. |
| Entity-only / deliberately empty result | Clause-local evaluation, persistence and policy retain cases without assertions and do not invent an edge merely to connect an entity. | T28, T31 | Absence of an assertion in a technical test is not a claim that a real clause should have none. |
| Conditions and exceptions | Later reverse references and exception candidates are reachable; selection gaps are visible; input fingerprints invalidate reuse when the candidate space changes. Evidence uses can mark condition/exception contribution without creating an ontology predicate. | T07, T11, T13-T14, T22, T26 | AP02 does not infer full Applicability or prove that a real model identifies every exception. |
| Normative force | Normative force is carried and evaluated as an assertion attribute independently of predicate identity and structural labels. | T27 | The tests check representation/evaluation behavior; actual force recognition is an AP03 model-quality question. |

## Synthetic structural, integrity and security cases

The AP02 reference matrix also covers technical cases that are not Golden semantic decisions:

- display labels and unresolved heading provenance (T02-T03);
- wrong-branch prevention, cycles, missing parents and unresolved references (T09-T10);
- context/target budget overflow and visible omission (T11-T12);
- source/input invalidation and deterministic fingerprints (T13-T15, T33);
- quote ambiguity, canonical offsets, unavailable excerpts and partial grounding failure (T16-T22);
- table/formula availability without invented textual evidence (T23-T24);
- extractor/verifier source-basis mismatch and conservative release boundaries (T25-T26, T30);
- native-vs-frozen evaluator source separation (T29);
- persistence and formal evidence resolution after reload (T31);
- authorization and edition boundaries for external/source-provider access (T32);
- fully offline deterministic AP01/AP02 gates (T34).

The authoritative machine-readable mapping is
`tests/fixtures/ap02/reference-test-matrix.json`. `tests/architecture/test_ap02_reference_matrix.py`
requires exactly T01 through T34 and verifies that every referenced pytest function exists.

## What this matrix does not establish

Series F performs no real extractor, verifier, cascade or embedding inference. It establishes that the
current contracts can carry the required structures, preserve provenance and evidence identity,
reject known invalid technical forms, and expose deterministic inspection data. It does **not**
establish precision, recall, F1, semantic evidence quality, Golden fitness of synthetic examples, or
prompt/model generalization. Those questions remain for AP03 under the existing separation between
Development and Holdout evidence.
