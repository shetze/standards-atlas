"""Synthetic human-Web contract tests; no production text or claimed reviewer labels."""

import json

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient
from test_review_package import make_review, publish

from standards_atlas.adapters.web.review_security import (
    ReviewWorkbenchHttpConfig,
    ViewReceipts,
)
from standards_atlas.adapters.web.review_workbench import create_review_workbench_app
from standards_atlas.application.review_workbench import ReviewWorkbenchService
from standards_atlas.application.review_workbench.journal import load_journal
from standards_atlas.application.review_workbench.model import DecisionSubmission
from standards_atlas.application.review_workbench.presentation import evidence_segments
from standards_atlas.application.semantic_qualification.review_package.assistance import (
    record_model_recommendations,
)
from standards_atlas.application.semantic_qualification.review_package.candidates import (
    build_candidate_index,
)
from standards_atlas.application.semantic_qualification.review_package.model import (
    EvidenceQuote,
    HumanDecisionInput,
    SemanticPredicate,
)
from standards_atlas.application.semantic_qualification.review_package.preparation_model import (
    AnnotationBatch,
    SelectionRequest,
)
from standards_atlas.application.semantic_qualification.review_package.selection import (
    apply_selection,
    submit_selection,
)
from standards_atlas.application.semantic_qualification.review_package.service import (
    load_review,
    record_proposal,
)


def fixture(tmp_path, *, body_limit=262_144):
    root, manifest, items, spec = make_review(tmp_path)
    service = ReviewWorkbenchService(root.parent)
    client = TestClient(
        create_review_workbench_app(
            service,
            ReviewWorkbenchHttpConfig(
                max_request_body_bytes=body_limit,
            ),
        ),
        base_url="http://127.0.0.1:8089",
    )
    token = client.get("/api/bootstrap").json()["csrf_token"]
    client.headers.update({"X-Atlas-CSRF": token})
    return root, service, client


def view(client, example_id=None, *, reviewer="Test human", handle="review"):
    if example_id is None:
        cases = client.get(f"/api/packages/{handle}/cases", params={"split": "development"})
        example_id = cases.json()["items"][0]["example_id"]
    response = client.get(
        f"/api/packages/{handle}/case",
        params={
            "example_id": example_id,
            "reviewer": reviewer,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def correction(data, *, attribute="role_semantics_present", value=False, status="corrected"):
    return {
        "example_id": data["source"]["example_id"],
        "attribute": attribute,
        "status": status,
        "predicate": {"equals": value} if status == "corrected" else None,
        "comment": "Synthetic browser decision, not a production reference.",
    }


def submit(client, data, decisions):
    return client.post(
        "/api/packages/review/decisions",
        json={
            "view_token": data["view_token"],
            "human_attested": True,
            "decisions": decisions,
        },
    )


def model_proposal(root, example_id, *, value=True, text=None):
    package, state = load_review(root)
    source = next(s for s in package.population if s.example_id == example_id)
    # Add exact quoted evidence when requested; evidence/offsets are resolved by Atlas.
    return record_model_recommendations(
        root,
        package_sha256=package.package_sha256,
        expected_revision=state.revision,
        batch=AnnotationBatch.model_validate(
            {
                "request_id": f"synthetic-{state.revision}",
                "actor": "synthetic-codex",
                "model": "synthetic-model",
                "recommendations": [
                    {
                        "example_id": example_id,
                        "source_sha256": source.source_sha256,
                        "attribute": "role_semantics_present",
                        "predicate": {"equals": value},
                        "rationale": "SENTINEL-MODEL-RATIONALE",
                        "evidence": [{"quote": text, "purpose": "support"}] if text else [],
                    }
                ],
            }
        ),
    )


def test_http_assets_and_package_overview_are_real_and_do_not_start_llm(tmp_path):
    root, service, client = fixture(tmp_path)
    for path, fragment in (
        ("/", "Review Workbench"),
        ("/assets/app.js", "human_attested"),
        ("/assets/app.css", "counterevidence"),
        ("/assets/editors.js", "must_be_empty"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert fragment in response.text
        assert "no-store" in response.headers["cache-control"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    response = client.get("/api/packages").json()
    assert response["items"][0]["handle"] == "review"
    package = client.get("/api/packages/review", params={"reviewer": "Test human"}).json()
    assert package["report"]["ready_for_publication"] is False
    assert package["capabilities"]["suite_publication"] is False
    assert "rules" in package
    assert load_review(root)[1].decisions == ()


def test_pagination_is_stable_and_does_not_drop_selected_cases(tmp_path):
    root, service, client = fixture(tmp_path)
    package, _ = load_review(root)
    result = []
    for offset in range(len(package.cases)):
        page = client.get("/api/packages/review/cases", params={"limit": 1, "offset": offset})
        assert page.status_code == 200
        result.extend(row["example_id"] for row in page.json()["items"])
    assert result == [case.example_id for case in package.cases]
    assert len(result) == len(set(result))


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 51},
        {"offset": -1},
        {"limit": "bad"},
        {"split": "wrong"},
        {"status": "published"},
        {"attribute": "invented"},
        {"q": "a" * 501},
    ],
)
def test_invalid_page_filters_are_rejected(tmp_path, params):
    _, _, client = fixture(tmp_path)
    assert client.get("/api/packages/review/cases", params=params).status_code == 400


def test_open_complete_and_attribute_filters_follow_human_values(tmp_path):
    root, service, client = fixture(tmp_path)
    data = view(client)
    assert submit(client, data, [correction(data)]).status_code == 200
    page = service.list_cases("review", status="open", attribute="role_semantics_present")
    assert data["source"]["example_id"] not in {r["example_id"] for r in page["items"]}
    page = service.list_cases("review", status="complete", attribute="role_semantics_present")
    assert page["total"] == 1
    assert service.list_cases("review", status="complete")["total"] == 0


def test_case_contains_complete_unmodified_text_context_ids_and_schema(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    package, _ = load_review(root)
    original = next(s for s in package.population if s.example_id == data["source"]["example_id"])
    assert data["source"]["text"] == original.text
    assert "".join(s["text"] for s in data["source_rendering"]["text"]) == original.text
    assert data["source"]["structure"] == original.structure.model_dump(mode="json")
    assert data["source_complete"] is True
    assert data["view_token"] and "view" not in data
    assert set(data["schemas"]) == set(package.profile.attributes)


def test_holdout_blindness_is_server_side_not_css(tmp_path):
    root, _, client = fixture(tmp_path)
    package, state = load_review(root)
    example_id = next(c.example_id for c in package.cases if c.split == "holdout")
    source = next(s for s in package.population if s.example_id == example_id)
    model_proposal(root, example_id, text=source.text)
    data = view(client, example_id)
    assert data["proposals"] == []
    assert data["holdout"]["blind"] is True
    assert not any(s["marks"] for s in data["source_rendering"]["text"])
    assert "SENTINEL-MODEL-RATIONALE" not in json.dumps(data)
    _, state = load_review(root)
    proposal = state.proposals[-1]
    assert (
        submit(
            client,
            data,
            [
                {
                    "example_id": example_id,
                    "attribute": proposal.attribute,
                    "status": "confirmed",
                    "proposal_sha256": proposal.proposal_sha256,
                }
            ],
        ).status_code
        == 400
    )


def test_holdout_reveal_requires_assessment_keeps_history_hidden_and_records_exposure(tmp_path):
    root, service, client = fixture(tmp_path)
    package, original = load_review(root)
    example_id = next(c.example_id for c in package.cases if c.split == "holdout")
    model_proposal(root, example_id)
    package, state = load_review(root)
    record_proposal(
        root,
        expected_revision=state.revision,
        example_id=example_id,
        attribute="primary_knowledge_kind",
        predicate=SemanticPredicate(equals="process"),
        producer="canonical-engineering-document",
        producer_kind="engineering",
        rationale="Current normalized enrichment under review.",
        provenance="synthetic engineering state",
    )
    before = (root / "review-state.json").read_bytes()
    data = view(client, example_id)
    assert (
        client.post(
            "/api/packages/review/reveal",
            json={
                "view_token": data["view_token"],
                "assessment": "  ",
            },
        ).status_code
        == 422
    )
    response = client.post(
        "/api/packages/review/reveal",
        json={
            "view_token": data["view_token"],
            "assessment": "My prior source-based assessment.",
        },
    )
    assert response.status_code == 200, response.text
    updated = view(client, example_id)
    assert updated["holdout"]["blind"] is False
    assert {p["producer_kind"] for p in updated["proposals"]} == {"model", "engineering"}
    assert "SENTINEL-MODEL-RATIONALE" in json.dumps(updated)
    assert view(client, example_id, reviewer="Another human")["proposals"] == []
    assert (root / "review-state.json").read_bytes() == before
    journal = load_journal(root, *load_review(root))
    assert len(journal.exposures) == 1
    assert journal.exposures[0].proposal_sha256s
    model_proposal(root, example_id, value=False)
    newer = view(client, example_id)
    assert len(newer["proposals"]) == 2
    assert {p["producer_kind"] for p in newer["proposals"]} == {"model", "engineering"}
    assert newer["holdout"]["unrevealed_recommendation_count"] == 1


def test_repeated_identical_reveal_is_idempotent(tmp_path):
    root, _, client = fixture(tmp_path)
    example_id = next(c.example_id for c in load_review(root)[0].cases if c.split == "holdout")
    data = view(client, example_id)
    payload = {"view_token": data["view_token"], "assessment": "Synthetic independent assessment"}
    for _ in range(2):
        assert client.post("/api/packages/review/reveal", json=payload).status_code == 200
    assert len(load_journal(root, *load_review(root)).exposures) == 1


def test_holdout_manual_decision_is_possible_without_revealing_model(tmp_path):
    root, _, client = fixture(tmp_path)
    example_id = next(c.example_id for c in load_review(root)[0].cases if c.split == "holdout")
    data = view(client, example_id)
    assert submit(client, data, [correction(data)]).status_code == 200
    assert view(client, example_id)["holdout"]["blind"] is True
    assert len(load_review(root)[1].decisions) == 1


def test_stale_reveal_cannot_expose_unseen_new_revision(tmp_path):
    root, _, client = fixture(tmp_path)
    example_id = next(c.example_id for c in load_review(root)[0].cases if c.split == "holdout")
    data = view(client, example_id)
    model_proposal(root, example_id)
    assert (
        client.post(
            "/api/packages/review/reveal",
            json={
                "view_token": data["view_token"],
                "assessment": "Synthetic assessment",
            },
        ).status_code
        == 409
    )
    assert not (root / "workbench/state.json").exists()


@pytest.mark.parametrize("value", [False, None, [], 1, "true", "yes"])
def test_human_attestation_must_be_explicit_boolean_true(value):
    with pytest.raises(ValidationError):
        DecisionSubmission.model_validate(
            {
                "human_attested": value,
                "view_token": "x",
                "decisions": [
                    {
                        "example_id": "e",
                        "attribute": "process_functions",
                        "status": "deferred",
                    }
                ],
            }
        )


def test_atomic_batch_invalid_later_field_writes_nothing(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    before = (root / "review-state.json").read_bytes()
    response = submit(
        client,
        data,
        [
            correction(data),
            correction(data, attribute="primary_function", value="NOT-A-CLASS"),
        ],
    )
    assert response.status_code in {400, 422}
    assert (root / "review-state.json").read_bytes() == before
    assert not (root / "history").exists()


def test_atomic_batch_duplicate_attribute_is_rejected(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    assert submit(client, data, [correction(data), correction(data)]).status_code == 400
    assert not load_review(root)[1].decisions


def test_explicit_false_null_empty_survive_a_single_atomic_batch(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    response = submit(
        client,
        data,
        [
            correction(data),
            correction(data, attribute="primary_function", value=None),
            correction(data, attribute="process_functions", value=[]),
        ],
    )
    assert response.status_code == 200, response.text
    reviews = view(client)["human_reviews"]
    values = {d["attribute"]: d["predicate"] for d in reviews}
    assert values["role_semantics_present"] == {"equals": False}
    assert values["primary_function"] == {"equals": None}
    assert values["process_functions"] == {"equals": []}
    assert len(list((root / "history").glob("*.json"))) == 1


def test_confirm_exact_displayed_proposal_and_stale_replay_does_not_duplicate(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    proposal = data["proposals"][0]
    decision = {
        "example_id": data["source"]["example_id"],
        "attribute": proposal["attribute"],
        "status": "confirmed",
        "proposal_sha256": proposal["proposal_sha256"],
    }
    assert submit(client, data, [decision]).status_code == 200
    assert submit(client, data, [decision]).status_code == 409
    assert len(load_review(root)[1].decisions) == 1
    assert load_review(root)[1].decisions[0].proposal_sha256 == proposal["proposal_sha256"]


def test_forged_view_and_foreign_case_are_rejected(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    forged = {**data, "view_token": data["view_token"] + "x"}
    assert submit(client, forged, [correction(data)]).status_code == 400
    other = next(
        c.example_id
        for c in load_review(root)[0].cases
        if c.example_id != data["source"]["example_id"]
    )
    assert submit(client, data, [{**correction(data), "example_id": other}]).status_code == 400
    assert not load_review(root)[1].decisions


def test_new_model_proposal_invalidates_old_display_without_replacing_existing_human(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    assert submit(client, data, [correction(data)]).status_code == 200
    prior = load_review(root)[1].decisions
    data = view(client)
    model_proposal(root, data["source"]["example_id"])
    assert submit(client, data, [correction(data, value=True)]).status_code == 409
    assert load_review(root)[1].decisions == prior


def test_rejected_and_deferred_stay_open(tmp_path):
    root, service, client = fixture(tmp_path)
    data = view(client)
    p = data["proposals"][0]
    response = submit(
        client,
        data,
        [
            {
                "example_id": data["source"]["example_id"],
                "attribute": p["attribute"],
                "status": "rejected",
                "proposal_sha256": p["proposal_sha256"],
            },
            correction(data, attribute="role_semantics_present", status="deferred"),
        ],
    )
    assert response.status_code == 200, response.text
    assert all(d.predicate is None for d in load_review(root)[1].decisions)
    assert service.list_cases("review", status="deferred")["total"] == 1


def test_bookmark_resumes_across_service_restart_without_review_writes(tmp_path):
    root, _, client = fixture(tmp_path)
    data = view(client)
    payload = {
        "reviewer": "Test human",
        "example_id": data["source"]["example_id"],
        "package_sha256": data["package_sha256"],
    }
    before = (root / "review-state.json").read_bytes()
    for _ in range(2):
        assert client.post("/api/packages/review/bookmark", json=payload).status_code == 200
    service = ReviewWorkbenchService(root.parent)
    resume = service.get_package("review", reviewer="Test human")["resume_example_id"]
    assert resume == payload["example_id"]
    assert service.get_package("review", reviewer="Other")["resume_example_id"] is None
    assert (root / "review-state.json").read_bytes() == before
    assert load_journal(root, *load_review(root)).revision == 1


def test_journal_tampering_is_detected_and_cannot_change_labels(tmp_path):
    root, service, client = fixture(tmp_path)
    data = view(client)
    client.post(
        "/api/packages/review/bookmark",
        json={
            "reviewer": "Test human",
            "example_id": data["source"]["example_id"],
            "package_sha256": data["package_sha256"],
        },
    )
    path = root / "workbench/state.json"
    value = json.loads(path.read_bytes())
    value["revision"] += 1
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="fingerprint"):
        service.get_package("review", reviewer="Test human")
    assert not load_review(root)[1].decisions


def test_evidence_overlaps_unicode_and_html_roundtrip_without_markup():
    text = 'A 🛤️ e\u0301 <script>alert("x")</script> Ω end'
    quote = '<script>alert("x")</script>'
    start = text.index(quote)
    spans = [
        {
            "start": start,
            "end": start + len(quote),
            "quote": quote,
            "attribute": "a",
            "purpose": "support",
            "proposal_sha256": "a" * 64,
        },
        {
            "start": start + 8,
            "end": start + 18,
            "quote": text[start + 8 : start + 18],
            "attribute": "b",
            "purpose": "counterevidence",
            "proposal_sha256": "b" * 64,
        },
    ]
    parts = evidence_segments(text, spans)
    assert "".join(p["text"] for p in parts) == text
    assert any(len(p["marks"]) == 2 for p in parts)
    assert all(set(p) == {"text", "marks"} for p in parts)
    with pytest.raises(ValueError, match="displayed frozen source"):
        evidence_segments(text, [{**spans[0], "quote": "wrong"}])


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example"},
        {"Origin": "https://evil.example"},
        {"Origin": "http://127.0.0.1:9999"},
        {"Origin": "null"},
        {"Origin": "http://localhost:8089"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
def test_cross_origin_reads_cannot_get_csrf_or_source(tmp_path, headers):
    _, _, client = fixture(tmp_path)
    response = client.get("/api/bootstrap", headers=headers)
    assert response.status_code == 403
    assert "csrf_token" not in response.json()
    assert "no-store" in response.headers["cache-control"]


def test_post_requires_csrf_json_and_no_cors_is_enabled(tmp_path):
    _, _, client = fixture(tmp_path)
    client.headers.pop("X-Atlas-CSRF")
    assert client.post("/api/packages/review/bookmark", json={}).status_code == 403
    token = client.get("/api/bootstrap").json()["csrf_token"]
    response = client.post(
        "/api/packages/review/bookmark",
        content="text",
        headers={"X-Atlas-CSRF": token},
    )
    assert response.status_code == 415
    response = client.options(
        "/api/packages/review/decisions",
        headers={"Origin": "https://evil.example"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_body_limit_malformed_json_and_unexpected_fields(tmp_path):
    _, _, client = fixture(tmp_path, body_limit=1024)
    response = client.post("/api/packages/review/decisions", json={"oversized": "a" * 2048})
    assert response.status_code == 413
    response = client.post(
        "/api/packages/review/decisions",
        content="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    data = view(client)
    response = client.post(
        "/api/packages/review/bookmark",
        json={
            "reviewer": "Test human",
            "example_id": data["source"]["example_id"],
            "package_sha256": data["package_sha256"],
            "human_confirmed": True,
        },
    )
    assert response.status_code == 422
    assert "details" in response.json()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.77", "::", "evil.example"])
def test_review_server_refuses_nonloopback(host):
    with pytest.raises(ValueError, match="loopback"):
        ReviewWorkbenchHttpConfig(host=host)


def test_registry_rejects_paths_symlinks_and_oversize_without_truncation(tmp_path):
    root, service, client = fixture(tmp_path)
    for handle in ("../review", str(root), ".", "review/nested"):
        with pytest.raises(ValueError, match="handle"):
            service.get_package(handle, reviewer="Test human")
    (root.parent / "alias").symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        service.get_package("alias", reviewer="Test human")
    tiny = ReviewWorkbenchService(root.parent, max_artifact_bytes=1)
    with pytest.raises(ValueError, match="not truncated"):
        tiny.get_package("review", reviewer="Test human")
    assert tiny.list_packages()["unavailable"]


def test_view_receipts_reject_tampering_other_sessions_and_non_ascii():
    receipts = ViewReceipts()
    token = receipts.sign({"example_id": "sample"})
    assert receipts.verify(token) == {"example_id": "sample"}
    for invalid in (token + "x", token.rsplit(".", 1)[0] + ".ä", "bad", "x" * 131073):
        with pytest.raises(ValueError, match="invalid or expired"):
            receipts.verify(invalid)
    with pytest.raises(ValueError):
        ViewReceipts().verify(token)


def test_no_publication_model_selection_or_rule_write_routes(tmp_path):
    _, _, client = fixture(tmp_path)
    for endpoint in ("publish", "import", "rules", "models", "selection", "proposals"):
        assert client.post(f"/api/packages/review/{endpoint}", json={}).status_code == 404


def test_completed_web_decisions_are_compatible_with_existing_suite_import(tmp_path):
    root, service, client = fixture(tmp_path)
    package, _ = load_review(root)
    values = {
        "primary_function": None,
        "primary_knowledge_kind": None,
        "role_semantics_present": False,
        "process_functions": [],
    }
    for case in package.cases:
        data = view(client, case.example_id)
        result = submit(
            client, data, [correction(data, attribute=a, value=values[a]) for a in case.attributes]
        )
        assert result.status_code == 200, result.text
    report = service.get_package("review", reviewer="Test human")["report"]
    assert report["ready_for_publication"] is True
    output = tmp_path / "published"
    publish(root, output)
    assert (output / "development.yaml").exists()
    assert (output / "holdout.yaml").exists()
    assert not (root / "development.yaml").exists()


def test_materialized_priority_queue_and_rationale_remain_fixed_during_review(tmp_path):
    root, service, client = fixture(tmp_path)
    package, state = load_review(root)
    index = build_candidate_index(root, additional_development_budget=0)
    sources = {s.example_id: s for s in package.population}
    dev = next(c.example_id for c in package.cases if c.split == "development")
    request = SelectionRequest.model_validate(
        {
            "actor": "test-agent",
            "model": "test-model",
            "rationale": "Synthetic priority order",
            "priorities": [
                {
                    "example_id": dev,
                    "source_sha256": sources[dev].source_sha256,
                    "priority": 95,
                    "rationale": "Difficult semantic boundary",
                }
            ],
        }
    )
    selection = submit_selection(
        root,
        index_sha256=index["index_sha256"],
        expected_state_sha256=state.state_sha256,
        request=request,
    )
    apply_selection(
        root,
        selection_sha256=selection["selection_sha256"],
        output=root.parent / "prioritized",
        review_id="prioritized",
    )
    before = service.list_cases("prioritized")["items"]
    data = service.get_case("prioritized", dev, reviewer="Synthetic human")
    assert data["priority"]["rationale"] == "Difficult semantic boundary"
    assert data["position"] == 0
    service.decide(
        "prioritized",
        view=data["view"],
        decisions=(
            HumanDecisionInput(
                example_id=dev,
                attribute="role_semantics_present",
                status="deferred",
            ),
        ),
    )
    assert [r["example_id"] for r in before] == [
        r["example_id"] for r in service.list_cases("prioritized")["items"]
    ]
    path = root.parent / "prioritized/review-queue.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="queue fingerprint"):
        service.list_cases("prioritized")


def test_anchor_locates_current_filtered_page_without_reordering(tmp_path):
    root, service, client = fixture(tmp_path)
    order = service.list_cases("review")["items"]
    page = service.list_cases("review", limit=1, offset=0, anchor=order[-1]["example_id"])
    assert page["offset"] == len(order) - 1
    assert page["items"][0]["example_id"] == order[-1]["example_id"]


def test_structural_evidence_targets_keep_original_fact_indices(tmp_path):
    root, service, client = fixture(tmp_path)
    package, state = load_review(root)
    case = next(c for c in package.cases if c.split == "development")
    source = next(s for s in package.population if s.example_id == case.example_id)
    index, fact = next(
        (i, f)
        for i, f in enumerate(source.structure.facts)
        if f.field == "heading" and isinstance(f.value, str)
    )
    record_proposal(
        root,
        expected_revision=state.revision,
        example_id=case.example_id,
        attribute="primary_knowledge_kind",
        predicate=SemanticPredicate(equals="process"),
        producer="Synthetic helper",
        producer_kind="engineering",
        rationale="Heading evidence",
        provenance="test-only",
        evidence=(EvidenceQuote(target=f"fact:{index}", quote=fact.value, purpose="context"),),
    )
    data = service.get_case("review", case.example_id, reviewer="Synthetic human")
    segments = data["source_rendering"]["facts"][f"fact:{index}"]
    assert "".join(s["text"] for s in segments) == fact.value
    assert segments[0]["marks"][0]["purpose"] == "context"


def test_writer_lock_returns_conflict_and_preserves_state(tmp_path):
    root, service, client = fixture(tmp_path)
    data = view(client)
    (root / ".review.lock").write_text("synthetic competing writer")
    try:
        response = submit(client, data, [correction(data)])
        assert response.status_code == 409
        assert not load_review(root)[1].decisions
    finally:
        (root / ".review.lock").unlink()
