"""Source-bound context, leakage, compatibility and request-identity contracts."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.model.source_structure import (
    SOURCE_PATHS,
    SourceStructure,
    SourceStructureFact,
)
from standards_atlas.application.semantic_qualification import request_builder
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.context_framing import (
    TAXONOMY_GROUNDED_V1,
    frame_cbox_context,
    frame_qualification_context,
)
from standards_atlas.application.semantic_qualification.context_projection import (
    render_cbox_context,
)
from standards_atlas.application.semantic_qualification.proposals import (
    ProposalRunConfig,
    SemanticTaskRepository,
)

RESOURCES = Path("src/standards_atlas/resources/semantic")
SNAPSHOTS = Path("tests/fixtures/context")
TEXT = (
    "Aim: detect faults.\nDescription: apply this analysis method.\n"
    "NOTE: Requirements in Clause 7 do not apply to this class of equipment."
)


def item(*, canonical=True):
    context = {
        "document_key": "TEST",
        "knowledge_domain": "functional-safety",
        "clause_id": "technique-1",
        "reference": "B.1.1",
        "heading": "Fault detection",
        "clause_type": "clause",
        "canonical_section": "annex",
        "annex_status": "informative",
        "document_categories": [
            {
                "taxonomy": "document.iec-directives-2",
                "version": "1.0.0",
                "category": "supplementary_elements",
            },
        ],
        "semantic_sections": [
            {
                "label": "Aim",
                "role": "aim",
                "start_offset": 0,
                "end_offset": TEXT.index("Description:"),
            },
            {
                "label": "Description",
                "role": "description",
                "start_offset": TEXT.index("Description:"),
                "end_offset": TEXT.index("NOTE:"),
            },
            {
                "label": "NOTE",
                "role": "note",
                "start_offset": TEXT.index("NOTE:"),
                "end_offset": len(TEXT),
            },
        ],
        "structural_context": {"node_kind": "leaf", "child_clause_ids": []},
        "ancestor_headings": [
            {"clause_id": "parent-1", "reference": "B.1", "heading": "Techniques and measures"},
            {"clause_id": "parent-2", "reference": "B", "heading": "Informative annex"},
        ],
    }
    if canonical:
        facts = []
        for key in (
            "heading",
            "clause_type",
            "canonical_section",
            "annex_status",
            "document_categories",
            "semantic_sections",
        ):
            facts.append(
                SourceStructureFact(
                    field=key,
                    value=context[key],
                    source_clause_id="technique-1",
                    source_reference="B.1.1",
                    source_path=SOURCE_PATHS[key],
                    origin="confirmed" if key == "heading" else "deterministic",
                    authority="reviewed-source" if key == "heading" else None,
                    generator=None if key == "heading" else "baseline-extractor",
                    evidence=("Local source audit only.",),
                )
            )
        facts.append(
            SourceStructureFact(
                field="node_kind",
                value="leaf",
                source_clause_id="technique-1",
                source_reference="B.1.1",
                source_path=SOURCE_PATHS["node_kind"],
            )
        )
        for index, parent in enumerate(context["ancestor_headings"], 1):
            facts.append(
                SourceStructureFact(
                    field="ancestor_heading",
                    value=parent["heading"],
                    source_clause_id=parent["clause_id"],
                    source_reference=parent["reference"],
                    source_path="baseline.heading",
                    distance=index,
                )
            )
        context["source_structure"] = SourceStructure(
            document_key="TEST",
            clause_id="technique-1",
            reference="B.1.1",
            content_hash=normalized_content_hash(TEXT),
            facts=tuple(facts),
        ).model_dump(mode="json")
    return {"content": {"text": TEXT, "hash": normalized_content_hash(TEXT)}, "context": context}


def config(**changes):
    return ProposalRunConfig(
        **{
            "task": "semantic-profile-classification",
            "task_version": "2.5.0",
            "corpus_id": "semantic-profile-v1",
            "dataset_version": "2.2.0",
            "prompt_version": "taxonomy-grounded-v1",
            "cbox_frame": "taxonomy-grounded-v1",
            "provider": "fake",
            "model": "test-model",
            "max_tokens": 512,
            **changes,
        }
    )


def request(data, *, template=None, **changes):
    cfg = config(**changes)
    prompt = PromptRepository(RESOURCES / "prompts").load(cfg.task, cfg.prompt_version)
    if template is not None:
        prompt = replace(prompt, user_template=template)
    task, _ = SemanticTaskRepository(RESOURCES / "tasks").load(cfg.task, cfg.task_version)
    return request_builder.build_proposal_request(cfg, prompt, data, task)


def fingerprint(result):
    return result.metadata["qualification_input_fingerprint"]


def fact(data, field, distance=0):
    return next(
        value
        for value in data["context"]["source_structure"]["facts"]
        if value["field"] == field and value["distance"] == distance
    )


def test_exact_source_frame_and_rendering_snapshot():
    result = request(item())
    expected = json.loads((SNAPSHOTS / "taxonomy-grounded-v1.json").read_text())
    assert result.metadata["framed_cbox"] == expected
    frame = frame_cbox_context(
        item()["context"],
        TAXONOMY_GROUNDED_V1,
        text=TEXT,
        content_hash=normalized_content_hash(TEXT),
    )
    assert render_cbox_context(frame) + "\n" == (SNAPSHOTS / "taxonomy-grounded-v1.txt").read_text()
    assert TEXT in result.user_prompt
    assert "Local source audit only" not in result.user_prompt
    assert "reviewed-source" not in result.user_prompt
    assert "baseline-extractor" not in result.user_prompt
    assert "primary_knowledge_kind" not in result.metadata["framed_cbox"]


@pytest.mark.parametrize("canonical", [True, False])
@pytest.mark.parametrize(
    "field",
    [
        "semantic",
        "enrichments",
        "expected",
        "gold",
        "golden_labels",
        "attribute_sources",
        "structural_roles",
        "subject_context",
        "context_routing",
        "reference_mentions",
        "eligibility",
        "decision_plan",
        "taxonomy_decisions",
        "role_relations",
    ],
)
def test_old_semantic_outputs_and_gold_cannot_change_model_input(canonical, field):
    original = item(canonical=canonical)
    changed = copy.deepcopy(original)
    changed["context"][field] = {"primary_function": "LEAK-TARGET", "applicability_present": True}
    changed["expected"] = {"primary_knowledge_kind": "LEAK-GOLD"}
    before, after = request(original), request(changed)
    assert after.user_prompt == before.user_prompt
    assert fingerprint(after) == fingerprint(before)
    assert "LEAK" not in json.dumps(after.metadata["framed_cbox"])
    assert after.metadata["clause_context"][field] == changed["context"][field]


@pytest.mark.parametrize("field", ["evidence", "generator", "authority"])
def test_audit_prose_is_not_model_input_or_cache_evidence(field):
    data = item()
    before = request(data)
    target = fact(data, "heading")
    target[field] = ["LEAK-AUDIT"] if field == "evidence" else "LEAK-AUDIT"
    after = request(data)
    assert after.user_prompt == before.user_prompt
    assert fingerprint(after) == fingerprint(before)


@pytest.mark.parametrize(
    "field,value",
    [
        ("heading", "New method"),
        ("clause_type", "term"),
        ("canonical_section", "body"),
        ("annex_status", "normative"),
        ("node_kind", "branch"),
    ],
)
def test_changed_visible_source_fact_invalidates_reuse(field, value):
    data = item()
    before = fingerprint(request(data))
    fact(data, field)["value"] = value
    if field in data["context"]:
        data["context"][field] = value
    assert fingerprint(request(data)) != before


def test_source_origin_and_taxonomy_version_change_request_identity():
    data = item()
    before = fingerprint(request(data))
    fact(data, "heading")["origin"] = "unattributed"
    assert fingerprint(request(data)) != before
    data = item()
    fact(data, "document_categories")["value"][0]["version"] = "2.0.0"
    assert fingerprint(request(data)) != before


def test_reordered_source_storage_or_renderer_only_changes_do_not_create_evidence(monkeypatch):
    data = item()
    before = request(data)
    data["context"]["source_structure"]["facts"].reverse()
    fact(data, "semantic_sections")["value"].reverse()
    monkeypatch.setattr(request_builder, "render_cbox_context", lambda _: "Changed prose only")
    after = request(data)
    assert before.user_prompt != after.user_prompt
    assert fingerprint(before) == fingerprint(after)


def test_document_categories_are_namespaced_deduplicated_and_order_independent():
    data = item()
    before = request(data)
    values = fact(data, "document_categories")["value"]
    values.extend(
        [
            values[0].copy(),
            {"taxonomy": "domain.functional-safety", "category": "LEAK-DOMAIN"},
            {"taxonomy": "semantic.profile", "category": "LEAK-SEMANTIC"},
            "LEAK-BARE-LABEL",
        ]
    )
    after = request(data)
    assert before.user_prompt == after.user_prompt
    assert fingerprint(before) == fingerprint(after)


def test_source_contract_does_not_fall_back_to_excluded_canonical_values():
    data = item()
    target = fact(data, "heading")
    target.update(origin="excluded", value=None)
    data["context"]["heading"] = "LEAK-LLM-HEADING"
    data["context"]["title"] = "LEAK-LEGACY-HEADING"
    result = request(data, template="{heading}|{context_text}|{metadata}|{context_json}")
    assert "LEAK" not in result.user_prompt
    assert "heading" not in result.metadata["framed_cbox"]


def test_historical_headings_remain_unattributed_with_canonical_alias_precedence():
    data = item(canonical=False)
    data["context"]["title"] = "LEAK-STALE-TITLE"
    result = request(data)
    assert "LEAK" not in result.user_prompt
    assert result.metadata["framed_cbox"]["structure_origin"] == "legacy-context"
    assert set(result.metadata["framed_cbox"]["structure_sources"].values()) == {"unattributed"}
    data["context"]["title"] = data["context"].pop("heading")
    assert fingerprint(request(data)) == fingerprint(result)
    data["context"]["heading"] = None
    assert "heading" not in request(data).metadata["framed_cbox"]


def test_legacy_structural_collection_extras_never_enter_prompt():
    data = item(canonical=False)
    before = request(data)
    data["context"]["document_categories"][0]["expected"] = "LEAK"
    data["context"]["semantic_sections"][0]["semantic"] = {"primary_function": "LEAK"}
    data["context"]["structural_context"]["scopes"] = ["LEAK"]
    after = request(data)
    assert before.user_prompt == after.user_prompt
    assert fingerprint(before) == fingerprint(after)


def test_ancestors_are_bounded_by_actual_distance_not_compacted_list_position():
    data = item()
    parents = data["context"]["source_structure"]["facts"]
    parents[:] = [entry for entry in parents if entry["field"] != "ancestor_heading"]
    for distance in (2, 4, 5):
        parents.append(
            SourceStructureFact(
                field="ancestor_heading",
                value=f"Parent {distance}",
                source_clause_id=f"p{distance}",
                source_reference=str(distance),
                source_path="baseline.heading",
                distance=distance,
            ).model_dump(mode="json")
        )
    before = request(data)
    visible = before.metadata["framed_cbox"]["ancestor_headings"]
    assert [parent["distance"] for parent in visible] == [2, 4]
    assert "distance 2" in before.user_prompt
    assert "immediate enclosing" not in before.user_prompt
    fact(data, "ancestor_heading", 5)["value"] = "LEAK-FAR-PARENT"
    assert fingerprint(request(data)) == fingerprint(before)
    fact(data, "ancestor_heading", 4)["value"] = "Changed visible parent"
    assert fingerprint(request(data)) != fingerprint(before)


@pytest.mark.parametrize(
    "bad",
    [
        {"start_offset": -1},
        {"end_offset": 999999},
        {"start_offset": True},
        {"start_offset": 10, "end_offset": 9},
        {"label": ""},
    ],
)
def test_invalid_segment_markers_are_omitted_without_losing_clause_text(bad):
    data = item()
    segments = fact(data, "semantic_sections")["value"]
    segments[0].update(bad)
    result = request(data)
    assert len(result.metadata["framed_cbox"]["semantic_sections"]) == 2
    assert TEXT in result.user_prompt
    assert "NOTE:" in result.user_prompt


def test_context_only_preview_does_not_claim_unvalidated_segment_ranges():
    frame = frame_cbox_context(item()["context"], TAXONOMY_GROUNDED_V1)
    assert "semantic_sections" not in frame.values
    assert frame.values["heading"] == "Fault detection"


def test_long_complete_clause_is_not_limited_to_marked_segments():
    data = item(canonical=False)
    text = TEXT + "\n" + "Unmarked content. " * 5000 + "\nNOTE: Last local normative statement."
    data["content"].update(text=text, hash=normalized_content_hash(text))
    result = request(data)
    assert text in result.user_prompt
    assert "Last local normative statement." in result.user_prompt


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "999"),
        ("clause_id", "wrong-clause"),
        ("document_key", "wrong-document"),
        ("reference", "99"),
        ("content_hash", "sha256:" + "0" * 64),
    ],
)
def test_bad_source_identity_is_rejected_before_request(field, value):
    data = item()
    data["context"]["source_structure"][field] = value
    with pytest.raises(ValueError):
        request(data)


def test_declared_content_hash_and_text_are_verified_for_new_frame():
    data = item()
    data["content"]["hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="content hash"):
        request(data)


def test_invalid_source_contract_cannot_embed_semantic_answers():
    data = item()
    fact(data, "semantic_sections")["value"][0]["primary_function"] = "LEAK"
    with pytest.raises(ValueError, match="non-structural"):
        request(data)


@pytest.mark.parametrize(
    "task",
    [
        "semantic-profile-classification",
        "context-routing-enrichment",
        "primary-subject-extraction",
        "unknown-future-task",
    ],
)
def test_taxonomy_frame_stays_source_only_for_all_qualification_tasks(task):
    data = item()
    data["context"]["semantic"] = {"primary_function": "LEAK"}
    data["context"]["subject_context"] = {"primary_subject": "LEAK"}
    data["context"]["context_routing"] = {"scopes": ["LEAK"]}
    frame = frame_qualification_context(
        data["context"],
        TAXONOMY_GROUNDED_V1,
        task=task,
        text=TEXT,
        content_hash=data["content"]["hash"],
    )
    assert "LEAK" not in json.dumps(frame.values)
    assert "semantic" not in frame.values
    assert "primary_subject" not in frame.values
