"""R4 real boundary regressions and synthetic MCP -> Web -> qualification evidence.

No external model, production label, browser engine or live MCP transport is used.
Registered typed MCP tool functions and the real Web ASGI routes are exercised.
"""

from __future__ import annotations

import hashlib
from zipfile import ZipFile

import pytest
from starlette.testclient import TestClient
from test_partial_observations import RESOURCES, prepared
from test_review_handoff import DECLARATION, VALUES
from test_review_package import make_review
from test_review_preparation import annotation_batch, report_file, selection_request
from test_review_workbench import correction, view

from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.adapters.mcp.review_tools import register_review_tools
from standards_atlas.adapters.web.review_security import ReviewWorkbenchHttpConfig
from standards_atlas.adapters.web.review_workbench import create_review_workbench_app
from standards_atlas.adapters.workflow.cli_renderer import CliWorkflowOperationRenderer
from standards_atlas.application.review_workbench import ReviewWorkbenchService
from standards_atlas.application.schema import SCHEMA_POLICIES, SchemaPolicy
from standards_atlas.application.semantic_qualification.campaign_activation import archive_campaign
from standards_atlas.application.semantic_qualification.campaign_evaluation import evaluate_campaign
from standards_atlas.application.semantic_qualification.campaign_execution import (
    FreshLedgerGateway,
    run_campaign,
)
from standards_atlas.application.semantic_qualification.campaign_selection import (
    load_campaign,
    prepare_campaign,
)
from standards_atlas.application.semantic_qualification.review_package.archive import (
    archive_review_package,
    verify_archive_bytes,
)
from standards_atlas.application.semantic_qualification.review_package.candidates import (
    build_candidate_index,
    load_candidate_index,
)
from standards_atlas.application.semantic_qualification.review_package.handoff import (
    create_review_handoff,
    load_review_handoff,
)
from standards_atlas.application.semantic_qualification.review_package.selection import (
    apply_selection,
    review_queue,
)
from standards_atlas.application.semantic_qualification.review_package.service import load_review
from standards_atlas.application.semantic_qualification.review_package.storage import write_state
from standards_atlas.application.workflow.partial_qualification_plan import (
    plan_partial_qualification,
)


def hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


_RENDERER = CliWorkflowOperationRenderer()


def _command(step) -> tuple[str, ...]:
    return _RENDERER.render(step.operation)


class ToolRegistry:
    """Transport-free registration double; does not pretend to be a Codex session."""

    def __init__(self):
        self.tools = {}

    def tool(self, **annotations):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn

        return register


def test_full_current_review_workflow_preserves_authority_and_archived_evidence(tmp_path):
    root, manifest, items, _ = make_review(tmp_path)
    history = tmp_path / "history/mixed-consensus-report.json"
    report_file(history, items, disagree=True)
    receipt = build_candidate_index(root, histories=(history,), additional_development_budget=1)
    package, state, index = load_candidate_index(root, receipt["index_sha256"])
    original_holdout = {c.example_id for c in package.cases if c.split == "holdout"}
    assert any(e.history for e in index.entries)
    config = McpServerConfig.model_validate(
        {
            "review": {
                "enabled": True,
                "workspace": str(tmp_path),
                "allow_holdout_assistance": True,
            },
            "capabilities": {"review_preparation": True},
        }
    )
    tools = ToolRegistry()
    register_review_tools(tools, config, lambda fn, *args, **kwargs: fn(*args, **kwargs))
    info = tools.tools["get_review_package"](root.name)
    assert info["capabilities"]["human_confirmation"] is False
    choice = tools.tools["submit_review_selection"](
        root.name,
        index.index_sha256,
        state.state_sha256,
        selection_request(package, index),
    )
    selected = tmp_path / "selected"
    apply_selection(
        root,
        selection_sha256=choice["selection_sha256"],
        output=selected,
        review_id="selected",
    )
    selected_package, state = load_review(selected)
    assert not state.decisions
    assert original_holdout == {
        c.example_id for c in selected_package.cases if c.split == "holdout"
    }
    assert len(selected_package.cases) == len(package.cases) + 1
    holdout = next(c for c in selected_package.cases if c.split == "holdout")
    for n, case in enumerate((selected_package.cases[0], holdout)):
        state = load_review(selected)[1]
        tools.tools["submit_review_annotations"](
            selected.name,
            selected_package.package_sha256,
            state.revision,
            annotation_batch(selected_package, case=case, request_id=f"r4-{n}", value=True),
        )
    assert not load_review(selected)[1].decisions
    assert not (selected / "development.yaml").exists()
    source = tools.tools["get_review_case"](selected.name, selected_package.cases[0].example_id)
    assert source["source_complete"] and source["source"]["text"]
    order = review_queue(selected, selected_package)
    app = create_review_workbench_app(
        ReviewWorkbenchService(tmp_path),
        ReviewWorkbenchHttpConfig(),
    )
    with TestClient(app, base_url="http://127.0.0.1:8089") as client:
        client.headers["X-Atlas-CSRF"] = client.get("/api/bootstrap").json()["csrf_token"]
        blind = view(client, holdout.example_id, handle=selected.name)
        assert not blind["proposals"]
        reveal = client.post(
            f"/api/packages/{selected.name}/reveal",
            json={
                "view_token": blind["view_token"],
                "assessment": "Synthetic source-only assessment.",
            },
        )
        assert reveal.status_code == 200, reveal.text
        assert view(client, holdout.example_id, handle=selected.name)["proposals"]
        assert not load_review(selected)[1].decisions
        for case in selected_package.cases:
            data = view(client, case.example_id, handle=selected.name)
            decisions = [correction(data, attribute=a, value=VALUES[a]) for a in case.attributes]
            response = client.post(
                f"/api/packages/{selected.name}/decisions",
                json={
                    "view_token": data["view_token"],
                    "human_attested": True,
                    "decisions": decisions,
                },
            )
            assert response.status_code == 200, response.text
    assert review_queue(selected, load_review(selected)[0]) == order
    confirmed_state = load_review(selected)[1]
    assert all(d.reviewer and d.status == "corrected" for d in confirmed_state.decisions)
    before = hashes(selected)
    handoff = tmp_path / "handoff"
    create_review_handoff(
        package=selected,
        manifest=manifest,
        output=handoff,
        resources=RESOURCES,
        holdout_declaration=DECLARATION,
    )
    assert hashes(selected) == before
    load_review_handoff(handoff, resources=RESOURCES)
    workflow = plan_partial_qualification(handoff / "campaign.yaml", tmp_path / "campaigns")
    assert "partial-review-check-handoff" in _command(workflow.steps[0])
    assert "partial-qualification-prepare" in _command(workflow.steps[1])
    campaign = tmp_path / "campaign"
    definition = prepare_campaign(
        manifest=handoff / "campaign.yaml",
        output=campaign,
        resources=RESOURCES,
    )
    assert definition["schema_version"] == "2.0"
    assert definition["review_evidence"] == {"kind": "archived_handoff"}
    frozen_before = hashes(campaign)
    planning = run_campaign(campaign=campaign, resources=RESOURCES, execute=False)
    assert planning["run_mode"] == "planned"
    assert hashes(campaign) == frozen_before
    suites = load_campaign(campaign, RESOURCES)[4]
    published_holdout = {c.example_id for s in suites if s.split == "holdout" for c in s.cases}
    assert published_holdout == original_holdout
    assert all(
        c.attributes["role_semantics_present"].equals is False for s in suites for c in s.cases
    )
    assert all(c.attributes["process_functions"].equals == [] for s in suites for c in s.cases)
    evaluation = evaluate_campaign(campaign=campaign, resources=RESOURCES)
    assert not evaluation["activation_eligible"]
    archive_path = archive_campaign(
        campaign=campaign,
        output=tmp_path / "archives",
        resources=RESOURCES,
    )
    with ZipFile(archive_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("inputs/review-package.zip"))
        snapshot = verify_archive_bytes(archive.read(name))
    assert snapshot.state.decisions == confirmed_state.decisions
    assert snapshot.workbench.state.exposures
    assert not list(tmp_path.rglob("activation.json"))
    assert all(hashes(campaign)[name] == sha for name, sha in frozen_before.items())


def test_event_writer_registry_drift_blocks_model_call_and_output(tmp_path, monkeypatch):
    class NeverCalled:
        called = False

        def generate_structured(self, request):
            self.called = True
            raise AssertionError("no model call allowed")

    request = prepared().request
    gateway = NeverCalled()
    ledger = FreshLedgerGateway(gateway, root=tmp_path, binding={}, model_id="synthetic")
    family = "qualification-request-event"
    monkeypatch.setitem(SCHEMA_POLICIES, family, SchemaPolicy(family, "2.0", ("2.0",), "test"))
    with pytest.raises(ValueError, match="writers may only emit"):
        ledger.generate_structured(request)
    assert not gateway.called and not list(tmp_path.iterdir())


def test_invalid_review_state_cannot_write_a_history_entry_before_rejection(tmp_path):
    root, *_ = make_review(tmp_path)
    _, state = load_review(root)
    before = hashes(root)
    with pytest.raises(ValueError, match="writers may only emit"):
        write_state(root, state, state.model_copy(update={"schema_version": "obsolete"}))
    assert hashes(root) == before


@pytest.mark.parametrize(
    "family",
    [
        "partial-review-package",
        "partial-review-profile",
        "partial-review-state",
        "partial-review-workbench-evidence",
        "review-workbench-state",
    ],
)
def test_registry_drift_cannot_publish_a_rebound_candidate_index(tmp_path, monkeypatch, family):
    root, *_ = make_review(tmp_path)
    before = hashes(root)
    monkeypatch.setitem(SCHEMA_POLICIES, family, SchemaPolicy(family, "2.0", ("2.0",), "test"))
    # Package/state changes fail already on reading; Workbench contracts are only
    # serialized by review publication, so use the archive/Handoff for those.
    with pytest.raises(ValueError):
        if family in {"partial-review-workbench-evidence", "review-workbench-state"}:
            archive_review_package(package=root, output=tmp_path / "review.zip")
        else:
            build_candidate_index(root)
    assert hashes(root) == before
    assert not (tmp_path / "review.zip").exists()
