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
        lambda workspace, context_config_path, progress=None: service,
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
        lambda workspace, context_config_path, progress=None: _ProgressService(progress),
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
