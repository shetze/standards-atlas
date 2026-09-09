"""Regression tests for document ontology classification LLM lifecycle."""

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from standards_atlas.cli.commands.document_commands import management


class _FakeServer:
    def __init__(self) -> None:
        self.start_calls = 0

    def start(self) -> None:
        self.start_calls += 1


@dataclass
class _FakeClassificationResult:
    document: object
    clauses_enriched: int
    candidates: int = 0
    subject_clauses: int = 0
    subjects_identified: int = 0
    subjects_ambiguous: int = 0
    context_enrichment_failures: int = 0


class _FakeClassificationService:
    def __init__(self, server: _FakeServer) -> None:
        self._server = server
        self.classify_calls: list[str] = []

    def enrich(self, document_key: str) -> _FakeClassificationResult:
        assert self._server.start_calls == 1
        self.classify_calls.append(document_key)
        document = SimpleNamespace(key=SimpleNamespace(value=document_key))
        return _FakeClassificationResult(document=document, clauses_enriched=3)


def test_classify_ontology_ensures_managed_llm_is_running(monkeypatch) -> None:
    server = _FakeServer()
    service = _FakeClassificationService(server)
    config = Path("cfg/context-enrichment.yaml")

    monkeypatch.setattr(management, "managed_llm_server", lambda path: server)
    monkeypatch.setattr(
        management,
        "build_context_enrichment_service",
        lambda workspace, context_config_path, progress=None, fresh=False: service,
    )

    management.enrich_document_context(
        "IEC61508-0",
        workspace=Path(".atlas"),
        context_config=config,
    )

    assert server.start_calls == 1
    assert service.classify_calls == ["IEC61508-0"]


def test_classify_ontology_reports_clause_progress(monkeypatch, capsys) -> None:
    from standards_atlas.application.services.context_enrichment_service import (
        ContextEnrichmentProgress,
    )

    server = _FakeServer()
    config = Path("cfg/context-enrichment.yaml")

    class _ProgressService:
        def __init__(self, progress) -> None:
            self._progress = progress

        def enrich(self, document_key: str) -> _FakeClassificationResult:
            self._progress(
                ContextEnrichmentProgress(
                    current=1,
                    total=1,
                    document_key=document_key,
                    clause_id="clause-1",
                    clause_reference="7.4.1",
                    clause_title="Verification",
                    state="started",
                )
            )
            self._progress(
                ContextEnrichmentProgress(
                    current=1,
                    total=1,
                    document_key=document_key,
                    clause_id="clause-1",
                    clause_reference="7.4.1",
                    clause_title="Verification",
                    state="partial",
                    elapsed_seconds=2.5,
                )
            )
            document = SimpleNamespace(key=SimpleNamespace(value=document_key))
            return _FakeClassificationResult(
                document=document,
                clauses_enriched=0,
                candidates=1,
                context_enrichment_failures=1,
            )

    monkeypatch.setattr(management, "managed_llm_server", lambda path: server)
    monkeypatch.setattr(
        management,
        "build_context_enrichment_service",
        lambda workspace, context_config_path, progress=None, fresh=False: _ProgressService(
            progress
        ),
    )

    management.enrich_document_context(
        "IEC61508-2",
        workspace=Path(".atlas"),
        context_config=config,
    )

    output = capsys.readouterr().out
    assert "Context enrichment     : starting for IEC61508-2" in output
    assert "[Enrich Document Context 001/001] 7.4.1 — Verification started" in output
    assert "[Enrich Document Context 001/001] 7.4.1 — Verification partial elapsed=2.5s" in output
    assert "Context failures      : 1" in output


def test_context_failures_write_private_diagnostics_and_success_clears_them(
    monkeypatch, tmp_path
) -> None:
    import json

    import pytest
    import typer

    server = _FakeServer()
    result = _FakeClassificationResult(
        document=SimpleNamespace(key=SimpleNamespace(value="IEC61508-0")),
        clauses_enriched=0,
        context_enrichment_failures=1,
    )
    result.routing_failures = ({"clause_id": "example", "rejected_content": "private response"},)
    monkeypatch.setattr(management, "managed_llm_server", lambda path: server)
    monkeypatch.setattr(
        management,
        "build_context_enrichment_service",
        lambda *a, **kw: SimpleNamespace(enrich=lambda key: result),
    )
    workspace = tmp_path / ".atlas/data"
    config = Path("cfg/context-enrichment.yaml")
    with pytest.raises(typer.Exit) as captured:
        management.enrich_document_context(
            "IEC61508-0", workspace=workspace, context_config=config, fail_on_failure=True
        )
    assert captured.value.exit_code == 2
    report = workspace / "evaluation/context-routing/IEC61508-0-failures.json"
    payload = json.loads(report.read_text())
    assert payload["failures"][0]["rejected_content"] == "private response"
    assert payload["prompt"].endswith("context-routing-v3")
    assert not (tmp_path / "data/enrichments").exists()
    result.context_enrichment_failures = 0
    result.routing_failures = ()
    management.enrich_document_context(
        "IEC61508-0", workspace=workspace, context_config=config, fail_on_failure=True
    )
    assert not report.exists()


def test_unresolved_target_report_is_not_a_generation_failure_and_is_cleared(
    monkeypatch, tmp_path, capsys
) -> None:
    import json

    server = _FakeServer()
    result = _FakeClassificationResult(
        document=SimpleNamespace(key=SimpleNamespace(value="IEC61508-0")),
        clauses_enriched=1,
    )
    result.unresolved_scope_targets = (
        {
            "source_clause_id": "source-4.9",
            "document_key": "IEC61508-2",
            "reference": "IEC 61508-2 Figure 2 and Table 1",
            "clause_id": None,
            "status": "unresolved",
        },
    )
    monkeypatch.setattr(management, "managed_llm_server", lambda path: server)
    monkeypatch.setattr(
        management,
        "build_context_enrichment_service",
        lambda *a, **kw: SimpleNamespace(enrich=lambda key: result),
    )
    workspace = tmp_path / ".atlas/data"
    management.enrich_document_context("IEC61508-0", workspace=workspace, fail_on_failure=True)
    output = capsys.readouterr().out
    assert "Context failures      : 0" in output
    assert "Scope targets unresolved: 1" in output
    report = workspace / "evaluation/context-routing/IEC61508-0-unresolved-targets.json"
    payload = json.loads(report.read_text())
    assert payload["unresolved_scope_targets"][0]["reference"] == (
        "IEC 61508-2 Figure 2 and Table 1"
    )
    assert not (workspace / "evaluation/context-routing/IEC61508-0-failures.json").exists()
    assert not (tmp_path / "data/enrichments").exists()
    result.unresolved_scope_targets = ()
    management.enrich_document_context("IEC61508-0", workspace=workspace, fail_on_failure=True)
    assert not report.exists()
    assert "Scope targets unresolved: 0" in capsys.readouterr().out
