"""AP03 Development-only MCP scope and read services.

The optimizer profile is deliberately narrower than the general MCP server.  Its authority is
constructed from the task-specific S08 assertion review packages, not from client supplied paths or
a document-only allowlist.  Development and Holdout source identities are checked before the server
is created so indirect readers cannot turn a mixed document into an unrestricted corpus view.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.application.assertion_qualification.assertion_review import (
    AssertionReviewWorkbenchCase,
    AssertionReviewWorkbenchPackage,
    AssertionReviewWorkbenchState,
    active_assertion_decisions,
    load_assertion_review_package,
)
from standards_atlas.application.assertion_qualification.experiment import (
    AssertionExperimentManifest,
    AssertionExperimentReport,
    manifest_sha256,
)
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    ClauseFilter,
    ClauseProvider,
    SamplingStrategy,
)

_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _safe_child(root: Path, name: str) -> Path:
    if not _SAFE_COMPONENT.fullmatch(name) or name in {".", ".."}:
        raise ValueError("invalid registered AP03 handle")
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError("AP03 Development roots must not contain symlinks")
    path = root / name
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("AP03 Development paths must not contain symlinks")
    return path


@dataclass(frozen=True)
class DevelopmentPackageView:
    handle: str
    package: AssertionReviewWorkbenchPackage
    state: AssertionReviewWorkbenchState
    cases: tuple[AssertionReviewWorkbenchCase, ...]
    view_sha256: str
    state_view_sha256: str


class McpDevelopmentScope:
    """Resolved server-side Development authority shared by every AP03 MCP reader."""

    def __init__(self, config: McpServerConfig) -> None:
        if not config.is_ap03_development or config.ap03_development is None:
            raise ValueError("AP03 Development scope requires profile='ap03-development'")
        self.config = config
        self._packages: dict[str, DevelopmentPackageView] = {}
        development_clause_ids: set[str] = set()
        holdout_clause_ids: set[str] = set()
        development_source_groups: set[str] = set()
        holdout_source_groups: set[str] = set()
        development_source_packages: set[str] = set()
        holdout_source_packages: set[str] = set()
        development_targets: set[tuple[str, str]] = set()

        for handle in config.ap03_development.review_handles:
            root = _safe_child(config.review.workspace, handle)
            if not root.is_dir():
                raise ValueError("registered AP03 assertion review package is unavailable")
            try:
                package, state = load_assertion_review_package(root)
            except (OSError, ValueError) as exc:
                raise ValueError("registered AP03 assertion review package is unavailable") from exc
            dev_cases = tuple(
                case for case in package.cases if case.partition.value == "development"
            )
            hold_cases = tuple(case for case in package.cases if case.partition.value == "holdout")
            if not dev_cases:
                raise ValueError("registered AP03 review package has no Development cases")
            for case in dev_cases:
                if case.document_key not in config.allowed_document_keys:
                    raise ValueError(
                        "AP03 Development review contains a document outside allowed_document_keys"
                    )
                development_targets.add((case.document_key, case.clause_id))
                development_source_groups.add(case.source_group)
                development_source_packages.add(case.source_package_sha256)
                development_clause_ids.update(surface.source_clause_id for surface in case.surfaces)
            for case in hold_cases:
                holdout_source_groups.add(case.source_group)
                holdout_source_packages.add(case.source_package_sha256)
                holdout_clause_ids.update(surface.source_clause_id for surface in case.surfaces)

            active = active_assertion_decisions(state)
            dev_state = [
                active[case.case_id].model_dump(mode="json")
                for case in dev_cases
                if case.case_id in active
            ]
            view_body = {
                "id": package.id,
                "version": package.version,
                "corpus_plan_sha256": package.corpus_plan_sha256,
                "ontology_versions": list(package.ontology_versions),
                "class_options": [item.model_dump(mode="json") for item in package.class_options],
                "predicate_options": [
                    item.model_dump(mode="json") for item in package.predicate_options
                ],
                "cases": [case.model_dump(mode="json") for case in dev_cases],
            }
            self._packages[handle] = DevelopmentPackageView(
                handle=handle,
                package=package,
                state=state,
                cases=dev_cases,
                view_sha256=_digest(view_body),
                state_view_sha256=_digest(dev_state),
            )

        overlap = development_clause_ids & holdout_clause_ids
        if overlap:
            raise ValueError(
                "Development and Holdout share source clauses; optimizer scope is unsafe"
            )
        if development_source_groups & holdout_source_groups:
            raise ValueError(
                "Development and Holdout share source groups; optimizer scope is unsafe"
            )
        if development_source_packages & holdout_source_packages:
            raise ValueError(
                "Development and Holdout share source packages; optimizer scope is unsafe"
            )
        if not development_clause_ids:
            raise ValueError("AP03 Development scope resolved no source clauses")

        self.allowed_clause_ids = frozenset(development_clause_ids)
        self.allowed_target_cases = frozenset(development_targets)
        self.allowed_source_package_sha256s = frozenset(development_source_packages)
        self.allowed_document_keys = frozenset(config.allowed_document_keys)
        self.allowed_experiment_ids = frozenset(config.ap03_development.experiment_ids)

    @property
    def handles(self) -> tuple[str, ...]:
        return tuple(sorted(self._packages))

    def package(self, handle: str) -> DevelopmentPackageView:
        try:
            return self._packages[handle]
        except KeyError as exc:
            raise ValueError("review package is outside the AP03 Development scope") from exc

    def ensure_clause_allowed(self, clause_id: str, document_key: str | None = None) -> None:
        if clause_id not in self.allowed_clause_ids:
            raise KeyError("source is not exposed by the AP03 Development profile")
        if document_key is not None and document_key not in self.allowed_document_keys:
            raise KeyError("source is not exposed by the AP03 Development profile")

    def ensure_experiment_allowed(self, experiment_id: str) -> None:
        if experiment_id not in self.allowed_experiment_ids:
            raise ValueError("experiment is outside the AP03 Development scope")

    def validate_manifest(self, manifest: AssertionExperimentManifest) -> None:
        self.ensure_experiment_allowed(manifest.experiment_id)
        if manifest.partition != "development":
            raise ValueError("AP03 optimizer may read Development experiments only")
        if self.config.ap03_development is None:
            raise ValueError("AP03 Development configuration is unavailable")
        if manifest.data_route not in self.config.ap03_development.allowed_data_routes:
            raise ValueError("experiment data route is not approved for the AP03 optimizer")
        for case in manifest.cases:
            if (case.document_key, case.clause_id) not in self.allowed_target_cases:
                raise ValueError("experiment contains a case outside the AP03 Development scope")
            if case.source_package_sha256 not in self.allowed_source_package_sha256s:
                raise ValueError("experiment source package is outside the AP03 Development scope")

    def allowed_clauses(self, provider: ClauseProvider) -> tuple[ClauseDescriptor, ...]:
        clause_ids = tuple(sorted(self.allowed_clause_ids))
        try:
            clauses = provider.get_clauses(
                clause_ids, document_keys=tuple(sorted(self.allowed_document_keys))
            )
        except KeyError as exc:
            raise ValueError("an AP03 Development source clause is unavailable") from exc
        if tuple(clause.id for clause in clauses) != clause_ids:
            raise ValueError("AP03 Development clause batch did not preserve exact requested ids")
        for clause in clauses:
            self.ensure_clause_allowed(clause.id, clause.document_key)
        return clauses

    def safe_clause_payload(
        self, clause: ClauseDescriptor, *, max_characters: int
    ) -> dict[str, Any]:
        self.ensure_clause_allowed(clause.id, clause.document_key)
        # Generic clause reads intentionally do not reproduce the document-wide CBox.  Exact
        # bearing context is exposed through the source-bound assertion review case instead.
        ancestor_headings = []
        for item in clause.ancestor_headings or ():
            if item.get("clause_id") in self.allowed_clause_ids:
                ancestor_headings.append(dict(item))
        return {
            "id": clause.id,
            "document_key": clause.document_key,
            "reference": clause.reference,
            "clause_reference": clause.clause_reference,
            "content_hash": clause.content_hash,
            "clause_type": clause.clause_type.value,
            "heading": clause.heading,
            "text": clause.text[:max_characters],
            "parent_id": clause.parent_id if clause.parent_id in self.allowed_clause_ids else None,
            "canonical_section": (
                clause.canonical_section.value if clause.canonical_section is not None else None
            ),
            "document_categories": list(clause.document_categories),
            "domain_categories": list(clause.domain_categories),
            "semantic_sections": [item.value for item in clause.semantic_sections],
            "content_profile": clause.content_profile.value,
            "table_block_count": clause.table_block_count,
            "table_text_length": clause.table_text_length,
            "non_table_text_length": clause.non_table_text_length,
            "ancestor_headings": ancestor_headings,
            "context_notice": (
                "Only source clauses explicitly present in the Development review package are "
                "visible here; use get_review_case for the bound bearing surfaces."
            ),
        }


class McpDevelopmentClauseView:
    """Clause discovery over the resolved Development set without searching hidden clauses."""

    def __init__(self, provider: ClauseProvider, scope: McpDevelopmentScope) -> None:
        self._provider = provider
        self._scope = scope
        self._limits = scope.config.limits
        self._allowed_clause_cache: tuple[ClauseDescriptor, ...] | None = None
        self._allowed_clause_index: dict[str, ClauseDescriptor] | None = None

    def _allowed_clauses(self) -> tuple[ClauseDescriptor, ...]:
        if self._allowed_clause_cache is None:
            clauses = self._scope.allowed_clauses(self._provider)
            self._allowed_clause_cache = clauses
            self._allowed_clause_index = {clause.id: clause for clause in clauses}
        return self._allowed_clause_cache

    def _allowed_clause(self, clause_id: str) -> ClauseDescriptor:
        self._scope.ensure_clause_allowed(clause_id)
        self._allowed_clauses()
        assert self._allowed_clause_index is not None
        return self._allowed_clause_index[clause_id]

    def list_documents(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for clause in self._allowed_clauses():
            counts[clause.document_key] = counts.get(clause.document_key, 0) + 1
        rows = []
        for item in self._provider.get_documents(tuple(sorted(counts))):
            rows.append(
                item.model_copy(update={"clause_count": counts[item.key]}).model_dump(mode="json")
            )
        return rows

    def get_clause(self, clause_id: str) -> dict[str, Any]:
        clause = self._allowed_clause(clause_id)
        return self._scope.safe_clause_payload(
            clause, max_characters=self._limits.max_clause_characters
        )

    def list_clauses(
        self,
        *,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        min_text_length: int | None = None,
        max_text_length: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._bounds(limit, offset)
        filters = ClauseFilter.model_validate(
            {
                "document_keys": tuple(document_keys or ()),
                "clause_types": tuple(clause_types or ()),
                "min_text_length": min_text_length,
                "max_text_length": max_text_length,
            }
        )
        clauses = [c for c in self._allowed_clauses() if _matches(c, filters)]
        return [
            self._scope.safe_clause_payload(c, max_characters=self._limits.max_clause_characters)
            for c in clauses[offset : offset + limit]
        ]

    def search_clauses(
        self,
        query: str,
        *,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self._bounds(limit, 0)
        terms = tuple(term.casefold() for term in query.split() if term.strip())
        if not terms:
            raise ValueError("query must not be empty")
        filters = ClauseFilter.model_validate(
            {
                "document_keys": tuple(document_keys or ()),
                "clause_types": tuple(clause_types or ()),
            }
        )
        matches: list[tuple[int, ClauseDescriptor]] = []
        for clause in self._allowed_clauses():
            if not _matches(clause, filters):
                continue
            title = (clause.heading or "").casefold()
            text = clause.text.casefold()
            reference = clause.reference.casefold()
            score = sum(3 for term in terms if term in title)
            score += sum(2 for term in terms if term in reference)
            score += sum(1 for term in terms if term in text)
            if score:
                matches.append((score, clause))
        matches.sort(key=lambda item: (-item[0], item[1].document_key, item[1].id))
        return [
            self._scope.safe_clause_payload(c, max_characters=self._limits.max_clause_characters)
            for _, c in matches[:limit]
        ]

    def sample_clauses(
        self,
        *,
        count: int,
        strategy: str = SamplingStrategy.RANDOM.value,
        seed: int = 0,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if count < 1 or count > self._limits.max_sample_size:
            raise ValueError("sample count is outside the configured Development limit")
        filters = ClauseFilter.model_validate(
            {
                "document_keys": tuple(document_keys or ()),
                "clause_types": tuple(clause_types or ()),
            }
        )
        population = [c for c in self._allowed_clauses() if _matches(c, filters)]
        if count > len(population):
            raise ValueError("sample count exceeds the exposed Development population")
        rng = random.Random(seed)
        if SamplingStrategy(strategy) is SamplingStrategy.RANDOM:
            chosen = rng.sample(population, count)
        elif SamplingStrategy(strategy) is SamplingStrategy.BALANCED_BY_DOCUMENT:
            buckets: dict[str, list[ClauseDescriptor]] = {}
            for clause in population:
                buckets.setdefault(clause.document_key, []).append(clause)
            for bucket in buckets.values():
                rng.shuffle(bucket)
            chosen = []
            while len(chosen) < count:
                for key in sorted(buckets):
                    if buckets[key] and len(chosen) < count:
                        chosen.append(buckets[key].pop())
                if not any(buckets.values()):
                    break
        else:
            raise ValueError("sampling strategy is not supported by the AP03 Development profile")
        return [
            self._scope.safe_clause_payload(c, max_characters=self._limits.max_clause_characters)
            for c in chosen
        ]

    def _bounds(self, limit: int, offset: int) -> None:
        if type(limit) is not int or not 1 <= limit <= self._limits.max_results:
            raise ValueError("limit exceeds configured AP03 Development maximum")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be non-negative")


class McpDevelopmentReviewService:
    """Read only the Development projection of the S08 assertion review packages."""

    def __init__(self, scope: McpDevelopmentScope) -> None:
        self._scope = scope
        self._limit = scope.config.limits.max_results

    def list_packages(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        self._bounds(limit, offset)
        rows = []
        for handle in self._scope.handles:
            view = self._scope.package(handle)
            rows.append(
                {
                    "handle": handle,
                    "id": view.package.id,
                    "version": view.package.version,
                    "task": "assertion_knowledge",
                    "development_case_count": len(view.cases),
                    "development_view_sha256": view.view_sha256,
                    "development_state_sha256": view.state_view_sha256,
                }
            )
        return {
            "total": len(rows),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "packages": rows[offset : offset + limit],
        }

    def get_package(self, handle: str) -> dict[str, Any]:
        view = self._scope.package(handle)
        return {
            "handle": handle,
            "id": view.package.id,
            "version": view.package.version,
            "task": "assertion_knowledge",
            "development_view_sha256": view.view_sha256,
            "development_state_sha256": view.state_view_sha256,
            "ontology_versions": list(view.package.ontology_versions),
            "class_options": [item.model_dump(mode="json") for item in view.package.class_options],
            "predicate_options": [
                item.model_dump(mode="json") for item in view.package.predicate_options
            ],
            "case_count": len(view.cases),
            "capabilities": {
                "human_confirmation": False,
                "suite_publication": False,
                "holdout_read": False,
                "model_inference_on_read": False,
            },
        }

    def list_cases(self, handle: str, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        self._bounds(limit, offset)
        view = self._scope.package(handle)
        rows = [
            {
                "case_id": case.case_id,
                "document_key": case.document_key,
                "clause_id": case.clause_id,
                "reference": case.reference,
                "source_group": case.source_group,
                "source_package_sha256": case.source_package_sha256,
            }
            for case in view.cases
        ]
        return {
            "development_view_sha256": view.view_sha256,
            "total": len(rows),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "cases": rows[offset : offset + limit],
        }

    def get_case(self, handle: str, case_id: str) -> dict[str, Any]:
        view = self._scope.package(handle)
        case = next((item for item in view.cases if item.case_id == case_id), None)
        if case is None:
            raise ValueError("review case is outside the AP03 Development scope")
        active = active_assertion_decisions(view.state)
        decision = active.get(case.case_id)
        return {
            "development_view_sha256": view.view_sha256,
            "development_state_sha256": view.state_view_sha256,
            "task": "assertion_knowledge",
            "source": {
                "case_id": case.case_id,
                "document_key": case.document_key,
                "clause_id": case.clause_id,
                "reference": case.reference,
                "source_group": case.source_group,
                "source_package_sha256": case.source_package_sha256,
                "surfaces": [surface.model_dump(mode="json") for surface in case.surfaces],
            },
            "proposal": case.proposal.model_dump(mode="json") if case.proposal else None,
            "human_review": decision.model_dump(mode="json") if decision else None,
            "human_confirmation_writable": False,
        }

    def _bounds(self, limit: int, offset: int) -> None:
        if type(limit) is not int or not 1 <= limit <= self._limit:
            raise ValueError("review page exceeds configured AP03 Development limit")
        if type(offset) is not int or offset < 0:
            raise ValueError("review offset must be non-negative")


class McpDevelopmentExperimentService:
    """Opaque-id reads for bound Development experiment manifests, states and reports."""

    def __init__(self, scope: McpDevelopmentScope) -> None:
        self._scope = scope
        cfg = scope.config.ap03_development
        assert cfg is not None
        self._repository = FileSystemAssertionExperimentRepository(
            cfg.project_root, scope.config.workspace
        )
        self._project_root = cfg.project_root
        self._limit = scope.config.limits.max_results

    def list_experiments(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= self._limit or offset < 0:
            raise ValueError("experiment page exceeds configured AP03 Development limit")
        rows = []
        for experiment_id in sorted(self._scope.allowed_experiment_ids):
            try:
                manifest = self._repository.load_manifest(experiment_id)
                self._scope.validate_manifest(manifest)
            except (OSError, ValueError):
                continue
            rows.append(
                {
                    "experiment_id": experiment_id,
                    "manifest_sha256": manifest_sha256(manifest),
                    "variant_id": manifest.variant_id,
                    "prompt_version": manifest.prompt_version,
                    "cases": len(manifest.cases),
                    "repetitions": manifest.repetitions,
                    "execution_authorized": manifest.execution_authorized,
                }
            )
        return {
            "total": len(rows),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "experiments": rows[offset : offset + limit],
        }

    def get_manifest(self, experiment_id: str) -> dict[str, Any]:
        manifest = self._manifest(experiment_id)
        payload = manifest.model_dump(mode="json")
        # Human authorization references are identifiers for Atlas, not optimizer instructions.
        payload["authorization_reference"] = None
        return payload

    def get_state(self, experiment_id: str) -> dict[str, Any]:
        manifest = self._manifest(experiment_id)
        state = self._repository.load_state(experiment_id)
        if state is None:
            return {
                "experiment_id": experiment_id,
                "manifest_sha256": manifest_sha256(manifest),
                "status": "not_run",
                "attempts": [],
                "completed_cells": [],
                "blocked_reason": None,
            }
        if state.manifest_sha256 != manifest_sha256(manifest):
            raise ValueError("experiment state is stale relative to its approved manifest")
        attempts = []
        for attempt in state.attempts:
            row = attempt.model_dump(mode="json")
            row["private_raw_artifact"] = None
            row["message"] = None
            attempts.append(row)
        return {
            "experiment_id": state.experiment_id,
            "manifest_sha256": state.manifest_sha256,
            "status": "recorded",
            "attempts": attempts,
            "completed_cells": list(state.completed_cells),
            "blocked_reason": state.blocked_reason,
        }

    def get_comparison(self, experiment_id: str) -> dict[str, Any]:
        manifest = self._manifest(experiment_id)
        path = (
            self._project_root
            / "local"
            / "evaluation"
            / "assertions"
            / "ap03"
            / experiment_id
            / "comparison.json"
        )
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("experiment report paths must not contain symlinks")
        if not path.is_file():
            raise ValueError("Development experiment comparison is unavailable")
        try:
            report = AssertionExperimentReport.model_validate_json(path.read_bytes())
        except (OSError, ValueError) as exc:
            raise ValueError("Development experiment comparison is unavailable") from exc
        if report.experiment_id != experiment_id or report.manifest_sha256 != manifest_sha256(
            manifest
        ):
            raise ValueError("experiment comparison is not bound to the approved manifest")
        return report.model_dump(mode="json")

    def _manifest(self, experiment_id: str) -> AssertionExperimentManifest:
        self._scope.ensure_experiment_allowed(experiment_id)
        root = self._project_root / "local" / "evaluation" / "assertions" / "ap03" / experiment_id
        if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
            raise ValueError("experiment paths must not contain symlinks")
        try:
            manifest = self._repository.load_manifest(experiment_id)
        except OSError as exc:
            raise ValueError("Development experiment manifest is unavailable") from exc
        self._scope.validate_manifest(manifest)
        return manifest


def _matches(clause: ClauseDescriptor, filters: ClauseFilter) -> bool:
    if filters.document_keys and clause.document_key not in filters.document_keys:
        return False
    if filters.clause_types and clause.clause_type not in filters.clause_types:
        return False
    length = len(clause.text)
    if filters.min_text_length is not None and length < filters.min_text_length:
        return False
    if filters.max_text_length is not None and length > filters.max_text_length:
        return False
    return True


class McpCodexOptimizationService:
    """Single controlled write surface for AP03 prompt proposals; never starts inference."""

    def __init__(self, scope: McpDevelopmentScope) -> None:
        from standards_atlas.adapters.mcp.codex_optimization import CodexPromptOptimizationService

        cfg = scope.config.ap03_development
        assert cfg is not None
        self._service = CodexPromptOptimizationService(
            project_root=cfg.project_root,
            workspace=scope.config.workspace,
            staging_directory=cfg.staging_directory,
            max_prompt_characters=cfg.max_prompt_characters,
            scope=scope,
        )

    def submit_prompt_variant_proposal(self, proposal: dict[str, object]) -> dict[str, object]:
        receipt = self._service.stage(proposal)
        return receipt.model_dump(mode="json")
