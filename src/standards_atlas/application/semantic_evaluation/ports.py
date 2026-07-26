"""Ports for semantic evaluation repositories."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import EvaluationReport, GoldenCorpus, PromptDefinition


class PromptRepository(Protocol):
    def load(self, identifier: str, version: str) -> PromptDefinition: ...


class GoldenCorpusRepository(Protocol):
    def load(self, identifier: str, version: str) -> GoldenCorpus: ...


class EvaluationReportRepository(Protocol):
    def save(self, report: EvaluationReport) -> Path: ...
