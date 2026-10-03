"""Filesystem adapter for the controlled AP03 Codex prompt-staging handoff."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemAssertionExperimentRepository
from standards_atlas.application.assertion_qualification.codex_optimization import (
    KNOWLEDGE_PROPOSAL_TASK,
    CodexOptimizationProposal,
    CodexOptimizationReceipt,
)
from standards_atlas.application.assertion_qualification.experiment import manifest_sha256
from standards_atlas.application.evaluation.repository import PromptRepository


def _canonical_sha256(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _assert_no_symlink_path(path: Path) -> None:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise ValueError("Codex staging paths must not contain symlinks")
        if current == current.parent:
            break
        current = current.parent


class CodexPromptOptimizationService:
    """Validate one model proposal and stage a prompt bundle at a server-owned path."""

    def __init__(
        self,
        *,
        project_root: Path,
        workspace: Path,
        staging_directory: Path,
        max_prompt_characters: int,
        scope: object,
    ) -> None:
        self._project_root = project_root.resolve()
        self._workspace = workspace
        self._staging_root = (
            staging_directory
            if staging_directory.is_absolute()
            else self._project_root / staging_directory
        ).resolve()
        self._max_prompt_characters = max_prompt_characters
        self._scope = scope
        allowed_staging_parent = (
            self._project_root / "local" / "evaluation" / "assertions" / "ap03"
        ).resolve()
        if not self._staging_root.is_relative_to(allowed_staging_parent):
            raise ValueError("AP03 Codex staging must stay under local/evaluation/assertions/ap03")
        _assert_no_symlink_path(self._staging_root)
        self._experiments = FileSystemAssertionExperimentRepository(project_root, workspace)
        semantic_root = Path(__file__).resolve().parents[2] / "resources" / "semantic"
        self._packaged_prompts = PromptRepository(
            semantic_root / "prompts",
            task_root=semantic_root / "tasks",
            policy_root=semantic_root / "policies",
            example_root=semantic_root / "examples",
        )
        self._semantic_root = semantic_root

    def stage(self, raw: CodexOptimizationProposal | dict[str, object]) -> CodexOptimizationReceipt:
        proposal = (
            raw
            if isinstance(raw, CodexOptimizationProposal)
            else CodexOptimizationProposal.model_validate(raw)
        )
        manifest = self._experiments.load_manifest(proposal.base_experiment_id)
        self._scope.validate_manifest(manifest)
        if not manifest.execution_authorized:
            raise ValueError(
                "Codex optimization requires an explicitly authorized Development plan"
            )
        digest = manifest_sha256(manifest)
        if digest != proposal.base_manifest_sha256:
            raise ValueError("Codex proposal is stale: base experiment manifest changed")
        if manifest.prompt_version != proposal.base_prompt_version:
            raise ValueError("Codex proposal base prompt does not match the bound experiment")
        if manifest.data_route != proposal.data_route:
            raise ValueError("Codex proposal data route differs from the approved experiment")
        if manifest.budget.max_calls < len(manifest.cases) * manifest.repetitions:
            raise ValueError("bound experiment budget cannot cover its planned cells")

        allowed_cases = {f"{case.document_key}:{case.clause_id}" for case in manifest.cases}
        allowed_clause_ids = {case.clause_id for case in manifest.cases}
        for cluster in proposal.error_clusters:
            for case_id in cluster.case_ids:
                if case_id not in allowed_cases and case_id not in allowed_clause_ids:
                    raise ValueError(
                        "Codex diagnostic cluster references a case outside the base plan"
                    )

        system_prompt = proposal.change.system_prompt.strip()
        if len(system_prompt) > self._max_prompt_characters:
            raise ValueError(
                "Codex prompt change exceeds the configured server-side character budget"
            )

        base = self._packaged_prompts.load(KNOWLEDGE_PROPOSAL_TASK, proposal.base_prompt_version)
        task_root = (
            self._semantic_root / "prompts" / KNOWLEDGE_PROPOSAL_TASK / proposal.base_prompt_version
        )
        if not task_root.is_dir():
            raise ValueError("Codex optimizer may modify only an installed packaged base prompt")
        base_role_prompt = (task_root / "system.txt").read_text(encoding="utf-8").strip()
        if system_prompt == base_role_prompt:
            raise ValueError("Codex prompt proposal is a no-op relative to its base role prompt")
        installed_target = (
            self._semantic_root
            / "prompts"
            / KNOWLEDGE_PROPOSAL_TASK
            / proposal.proposed_prompt_version
        )
        if installed_target.exists():
            raise ValueError("proposed prompt version conflicts with an installed prompt bundle")

        target = (
            self._staging_root
            / "prompts"
            / KNOWLEDGE_PROPOSAL_TASK
            / proposal.proposed_prompt_version
        )
        _assert_no_symlink_path(target)
        proposal_payload = proposal.model_dump(mode="json")
        proposal_hash = _canonical_sha256(proposal_payload)
        if target.exists():
            receipt = self._read_existing_receipt(target)
            actual_bundle_hash = self._bundle_sha256(target)
            if actual_bundle_hash != receipt.staged_bundle_sha256:
                raise ValueError("existing staged prompt no longer matches its Atlas receipt")
            if (
                receipt.request_id == proposal.request_id
                and receipt.proposal_sha256 == proposal_hash
            ):
                return receipt
            raise ValueError("proposed prompt version already exists with different content")

        self._staging_root.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_path(self._staging_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_path(target.parent)
        temp_root = Path(tempfile.mkdtemp(prefix=".codex-staging-", dir=self._staging_root))
        temp = temp_root / "prompts" / KNOWLEDGE_PROPOSAL_TASK / proposal.proposed_prompt_version
        temp.mkdir(parents=True, exist_ok=False)
        try:
            for name in ("schema.json", "user.txt"):
                shutil.copyfile(task_root / name, temp / name)
            metadata = json.loads((task_root / "prompt.json").read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("base prompt metadata must be a JSON object")
            metadata.update(
                {
                    "task": KNOWLEDGE_PROPOSAL_TASK,
                    "version": proposal.proposed_prompt_version,
                    "variant_id": proposal.proposed_variant_id,
                    "baseline_id": metadata.get("baseline_id") or proposal.base_prompt_version,
                    "qualification_status": "unqualified-development",
                    "description": (
                        "AP03 Codex-staged Development variant from "
                        f"{proposal.base_prompt_version}; "
                        f"request {proposal.request_id}."
                    ),
                }
            )
            (temp / "prompt.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (temp / "system.txt").write_text(system_prompt + "\n", encoding="utf-8")

            staged_repository = PromptRepository(
                temp_root / "prompts",
                task_root=self._semantic_root / "tasks",
                policy_root=self._semantic_root / "policies",
                example_root=self._semantic_root / "examples",
            )
            staged = staged_repository.load(
                KNOWLEDGE_PROPOSAL_TASK, proposal.proposed_prompt_version
            )
            if staged.output_schema != base.output_schema:
                raise ValueError("Codex proposal cannot change the task output schema")
            if staged.user_template != base.user_template:
                raise ValueError("Codex proposal cannot change the source-bound user template")
            if (
                staged.policy_sha256 != base.policy_sha256
                or staged.example_set_sha256 != base.example_set_sha256
            ):
                raise ValueError("Codex proposal cannot change policy/example bindings")

            bundle_hash = self._bundle_sha256(temp)
            relative = (
                target.relative_to(self._project_root).as_posix()
                if target.is_relative_to(self._project_root)
                else target.as_posix()
            )
            receipt = CodexOptimizationReceipt(
                request_id=proposal.request_id,
                proposal_sha256=proposal_hash,
                base_experiment_id=proposal.base_experiment_id,
                base_manifest_sha256=digest,
                base_prompt_version=proposal.base_prompt_version,
                proposed_prompt_version=proposal.proposed_prompt_version,
                proposed_variant_id=proposal.proposed_variant_id,
                staged_bundle_relative_path=relative,
                staged_bundle_sha256=bundle_hash,
                inherited_partition=manifest.partition,
                inherited_data_route=manifest.data_route,
                inherited_model_route=manifest.model_route,
                inherited_budget=manifest.budget.model_dump(mode="json"),
            )
            (temp / "staging-receipt.json").write_text(
                json.dumps(
                    receipt.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temp, target)
            return receipt
        finally:
            if temp_root.exists():
                shutil.rmtree(temp_root, ignore_errors=True)

    @staticmethod
    def _bundle_sha256(root: Path) -> str:
        digest = hashlib.sha256()
        for name in ("prompt.json", "schema.json", "system.txt", "user.txt"):
            path = root / name
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _read_existing_receipt(root: Path) -> CodexOptimizationReceipt:
        path = root / "staging-receipt.json"
        if not path.is_file():
            raise ValueError("existing staged prompt has no Atlas receipt")
        return CodexOptimizationReceipt.model_validate_json(path.read_bytes())
