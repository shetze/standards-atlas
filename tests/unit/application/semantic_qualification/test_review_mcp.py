"""MCP preparation adapter contracts without requiring an installed MCP transport SDK."""

import asyncio
import inspect
import json
from typing import get_type_hints

import pytest
from test_review_package import make_review
from test_review_preparation import annotation_batch, selection_request

from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.adapters.mcp.review import McpReviewService
from standards_atlas.adapters.mcp.review_tools import register_review_tools
from standards_atlas.application.semantic_qualification.review_package.candidates import (
    build_candidate_index,
    load_candidate_index,
)
from standards_atlas.application.semantic_qualification.review_package.service import load_review


def service_fixture(tmp_path, *, write=True, holdout=False, **config_overrides):
    root, _, _, _ = make_review(tmp_path)
    config = McpServerConfig.model_validate(
        {
            "review": {
                "enabled": True,
                "workspace": str(tmp_path),
                "allow_holdout_assistance": holdout,
            },
            "capabilities": {"review_preparation": write},
            **config_overrides,
        }
    )
    return root, McpReviewService(config)


@pytest.mark.parametrize("action", ["packages", "read", "write"])
def test_review_interface_off_by_default(tmp_path, action):
    root, _, _, _ = make_review(tmp_path)
    service = McpReviewService(McpServerConfig())
    with pytest.raises(ValueError, match="disabled"):
        if action == "packages":
            service.list_packages()
        elif action == "read":
            service.get_case(root.name, "g008")
        else:
            service.submit_annotations(
                root.name, package_sha256="0" * 64, expected_revision=0, batch={}
            )


def test_registry_rules_full_sources_and_no_internal_paths(tmp_path):
    root, service = service_fixture(tmp_path)
    index = build_candidate_index(root)
    catalog = service.list_packages()
    assert [p["handle"] for p in catalog["packages"]] == [root.name]
    info = service.get_package(root.name)
    assert info["indexes"][0]["index_sha256"] == index["index_sha256"]
    assert info["indexes"][0]["additional_development_budget"] == 20
    assert info["limits"]["max_results"] == service.config.limits.max_results
    assert info["rules"] and info["output_schema"]["properties"]
    assert info["capabilities"]["human_confirmation"] is False
    assert str(tmp_path) not in json.dumps(info)
    case = load_review(root)[0].known_development_ids[0]
    detail = service.get_case(root.name, case)
    assert detail["source_complete"] and detail["proposals"] and not detail["human_reviews"]
    assert str(tmp_path) not in json.dumps(detail)
    assert "input_files" not in detail


@pytest.mark.parametrize("handle", ["../review", "/tmp/review", ".", "..", "a/b", "a\\b", ""])
def test_registry_rejects_arbitrary_paths(tmp_path, handle):
    _, service = service_fixture(tmp_path)
    with pytest.raises(ValueError, match="handle"):
        service.get_package(handle)


def test_registry_refuses_symlinked_packages_and_artifacts(tmp_path):
    root, service = service_fixture(tmp_path)
    (tmp_path / "linked").symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        service.get_package("linked")
    built = build_candidate_index(root)
    directory = root / "preparation" / "indexes" / built["index_sha256"]
    path = directory / "index.json"
    moved = tmp_path / "stolen-index.json"
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(ValueError, match="symlink"):
        service.list_candidates(root.name, built["index_sha256"])


def test_document_allowlist_applies_to_whole_review_package(tmp_path):
    root, service = service_fixture(tmp_path, allowed_document_keys=["OTHER"])
    assert service.list_packages()["packages"] == []
    with pytest.raises(ValueError, match="allowlist"):
        service.get_package(root.name)


def test_no_review_bypass_when_clause_text_exposure_disabled(tmp_path):
    root, service = service_fixture(tmp_path, expose={"clause_text": False})
    with pytest.raises(ValueError, match="clause-text"):
        service.list_packages()
    with pytest.raises(ValueError, match="clause-text"):
        service.get_case(root.name, "g008")


def test_full_source_limit_rejects_instead_of_truncating(tmp_path):
    root, service = service_fixture(tmp_path, limits={"max_clause_characters": 5})
    package, state = load_review(root)
    with pytest.raises(ValueError, match="full review source"):
        service.get_case(root.name, package.known_development_ids[0])
    with pytest.raises(ValueError, match="full source"):
        service.submit_annotations(
            root.name,
            package_sha256=package.package_sha256,
            expected_revision=state.revision,
            batch=annotation_batch(package),
        )
    assert load_review(root)[1] == state


@pytest.mark.parametrize("limit,offset", [(0, 0), (-1, 0), (21, 0), (True, 0), (1, -1), (1, False)])
def test_bounds_checked_at_adapter(tmp_path, limit, offset):
    _, service = service_fixture(tmp_path)
    with pytest.raises(ValueError, match="bounds"):
        service.list_packages(limit=limit, offset=offset)


def test_read_only_capability_cannot_submit(tmp_path):
    root, service = service_fixture(tmp_path, write=False)
    package, state = load_review(root)
    with pytest.raises(ValueError, match="submissions are disabled"):
        service.submit_annotations(
            root.name,
            package_sha256=package.package_sha256,
            expected_revision=state.revision,
            batch=annotation_batch(package),
        )
    assert service.get_package(root.name)["capabilities"]["model_suggestions"] is False


def test_holdout_read_write_and_order_require_local_optin(tmp_path):
    root, service = service_fixture(tmp_path)
    package, state = load_review(root)
    case = next(c for c in package.cases if c.split == "holdout")
    with pytest.raises(ValueError, match="holdout"):
        service.get_case(root.name, case.example_id)
    with pytest.raises(ValueError, match="holdout"):
        service.list_cases(root.name, split="holdout")
    with pytest.raises(ValueError, match="holdout"):
        service.submit_annotations(
            root.name,
            package_sha256=package.package_sha256,
            expected_revision=state.revision,
            batch=annotation_batch(package, case=case),
        )
    config = service.config.model_copy(
        update={
            "review": service.config.review.model_copy(update={"allow_holdout_assistance": True})
        }
    )
    enabled = McpReviewService(config)
    detail = enabled.get_case(root.name, case.example_id)
    assert detail["holdout_prior_results_withheld"]
    assert detail["human_reviews"] == detail["proposals"] == []
    assert enabled.list_cases(root.name, split="holdout")["total"] == 2
    enabled.submit_annotations(
        root.name,
        package_sha256=package.package_sha256,
        expected_revision=state.revision,
        batch=annotation_batch(package, case=case),
    )
    assert load_review(root)[1].decisions == ()


def test_model_can_submit_selection_then_annotations_without_approving(tmp_path):
    root, service = service_fixture(tmp_path)
    result = build_candidate_index(root)
    package, state, index = load_candidate_index(root, result["index_sha256"])
    request = selection_request(package, index)
    receipt = service.submit_selection(
        root.name,
        index_sha256=index.index_sha256,
        expected_state_sha256=state.state_sha256,
        request=request,
    )
    assert receipt["human_decisions_added"] == 0
    annotation = service.submit_annotations(
        root.name,
        package_sha256=package.package_sha256,
        expected_revision=state.revision,
        batch=annotation_batch(package),
    )
    assert annotation["human_decisions_added"] == 0
    assert load_review(root)[1].decisions == ()
    assert not (root / "development.yaml").exists()


def test_typed_api_and_transport_registration_only_expose_model_writes(tmp_path):
    _, service = service_fixture(tmp_path)

    class Recorder:
        def __init__(self):
            self.tools = {}

        def tool(self, **options):
            def register(fn):
                self.tools[fn.__name__] = (fn, options)
                return fn

            return register

    server = Recorder()
    register_review_tools(server, service.config, lambda fn, *a, **kw: fn(*a, **kw))
    from standards_atlas.adapters.mcp.codex import REVIEW_PREPARATION_TOOLS

    assert set(server.tools) == set(REVIEW_PREPARATION_TOOLS)
    assert set(server.tools) == {
        "list_review_packages",
        "get_review_package",
        "list_review_candidates",
        "get_review_case",
        "list_review_cases",
        "submit_review_selection",
        "submit_review_annotations",
    }
    for name, (fn, options) in server.tools.items():
        hints = get_type_hints(fn)
        assert hints
        assert options["annotations"]["readOnlyHint"] == (not name.startswith("submit_"))
        assert not options["annotations"]["destructiveHint"]
        for forbidden in ("reviewer", "status", "output", "path", "producer_kind"):
            assert forbidden not in inspect.signature(fn).parameters
    annotate = server.tools["submit_review_annotations"][0]
    schema = get_type_hints(annotate)["batch"].model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"request_id", "actor", "model", "recommendations"}
    restricted = Recorder()
    register_review_tools(
        restricted,
        service.config.model_copy(
            update={
                "capabilities": service.config.capabilities.model_copy(
                    update={"review_preparation": False}
                )
            }
        ),
        lambda fn, *a, **kw: fn(*a, **kw),
    )
    assert len(restricted.tools) == 5


def test_actual_fastmcp_registration_and_tool_call_when_sdk_available(tmp_path):
    pytest.importorskip("mcp")
    from mcp.server.fastmcp import FastMCP

    root, service = service_fixture(tmp_path)
    server = FastMCP("review-contract-test")
    register_review_tools(server, service.config, lambda fn, *a, **kw: fn(*a, **kw))
    tools = asyncio.run(server.list_tools())
    assert len(tools) == 7
    result = asyncio.run(server.call_tool("get_review_package", {"handle": root.name}))
    assert result is not None


def test_selection_cannot_smuggle_holdout_priority_without_optin(tmp_path):
    root, service = service_fixture(tmp_path)
    result = build_candidate_index(root)
    package, state, index = load_candidate_index(root, result["index_sha256"])
    data = selection_request(package, index).model_dump(mode="json")
    holdout = next(e for e in index.entries if e.membership == "holdout")
    data["priorities"].append(
        dict(
            example_id=holdout.example_id,
            source_sha256=holdout.source_sha256,
            priority=100,
            rationale="Override reserved review order",
        )
    )
    with pytest.raises(ValueError, match="holdout"):
        service.submit_selection(
            root.name,
            index_sha256=index.index_sha256,
            expected_state_sha256=state.state_sha256,
            request=data,
        )


def test_stdio_service_enforces_payload_limit_before_writing(tmp_path):
    root, service = service_fixture(tmp_path, limits={"max_request_body_bytes": 1024})
    package, state = load_review(root)
    batch = annotation_batch(package).model_dump(mode="json")
    batch["recommendations"][0]["rationale"] = "Synthetic long explanation. " * 100
    before = (root / "review-state.json").read_bytes()
    with pytest.raises(ValueError, match="payload size limit"):
        service.submit_annotations(
            root.name,
            package_sha256=package.package_sha256,
            expected_revision=state.revision,
            batch=batch,
        )
    assert (root / "review-state.json").read_bytes() == before
