"""Codex CLI adapter for schema-constrained semantic evaluation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


@dataclass(frozen=True)
class CodexCliConfig:
    executable: str = "codex"
    timeout_seconds: int = 300
    sandbox: str = "read-only"
    # Codex-as-optimizer is a separate MCP client.  Direct model inference through this legacy
    # gateway remains disabled unless a caller explicitly opts into the non-qualifying arm.
    allow_uncontrolled_inference: bool = False


class CodexCliLlmGateway:
    """Invoke ``codex exec`` and capture its final structured message."""

    provider = "codex-cli"

    def __init__(self, config: CodexCliConfig | None = None) -> None:
        if config is None:
            config = CodexCliConfig()
        self._config = config

    def health(self) -> LlmHealth:
        try:
            completed = subprocess.run(
                [self._config.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return LlmHealth(False, detail=str(exc))
        detail = (completed.stdout or completed.stderr).strip()
        return LlmHealth(completed.returncode == 0, detail=detail)

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        if not self._config.allow_uncontrolled_inference:
            raise RuntimeError(
                "direct Codex CLI inference is disabled: use the AP03 optimizer client profile; "
                "this gateway is not a controlled qualification arm"
            )
        if not request.model:
            raise RuntimeError(
                "direct Codex CLI inference requires an explicit model; "
                "default model selection is uncontrolled"
            )
        if request.temperature != 0.0:
            raise RuntimeError("Codex CLI gateway cannot effectively set temperature")
        if request.seed is not None:
            raise RuntimeError("Codex CLI gateway cannot effectively set seed")
        if request.max_tokens is not None:
            raise RuntimeError("Codex CLI gateway cannot effectively set max_tokens")
        if request.reasoning_enabled is not None:
            raise RuntimeError("Codex CLI gateway cannot effectively set reasoning_enabled")
        model = request.model
        with tempfile.TemporaryDirectory(prefix="standards-atlas-codex-") as directory:
            root = Path(directory)
            schema_path = root / "schema.json"
            output_path = root / "response.json"
            schema_path.write_text(
                json.dumps(dict(request.output_schema), indent=2), encoding="utf-8"
            )
            prompt = f"{request.system_prompt}\n\n{request.user_prompt}\n"
            command = [
                self._config.executable,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                self._config.sandbox,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
            ]
            if request.model:
                command.extend(["--model", request.model])
            command.append("-")
            started = time.monotonic()
            try:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self._config.timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RuntimeError(f"Codex CLI invocation failed: {exc}") from exc
            duration_ms = round((time.monotonic() - started) * 1000)
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(f"Codex CLI exited with {completed.returncode}: {detail}")
            raw = output_path.read_text(encoding="utf-8").strip()
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Codex final message is not valid JSON") from exc
            if not isinstance(value, dict):
                raise RuntimeError("Codex final message must be a JSON object")
            input_hash = _request_hash(request, model)
            return StructuredGenerationResult(
                value=value,
                model=model,
                provider=self.provider,
                prompt_version=request.prompt_version,
                input_hash=input_hash,
                raw_response_hash=hashlib.sha256(raw.encode()).hexdigest(),
                duration_ms=duration_ms,
                raw_response={
                    "final_message": raw,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "parameter_provenance": {
                        "model": "effective_cli_argument",
                        "temperature": "not_controllable_by_gateway",
                        "seed": "not_controllable_by_gateway",
                        "max_tokens": "not_controllable_by_gateway",
                        "reasoning_enabled": "not_controllable_by_gateway",
                    },
                    "qualification_eligible": False,
                },
            )


def _request_hash(request: StructuredGenerationRequest, model: str) -> str:
    payload = {
        "task": request.task,
        "system_prompt": request.system_prompt,
        "user_prompt": request.user_prompt,
        "schema": request.output_schema,
        "prompt_version": request.prompt_version,
        "model": model,
        # Only invocation-effective inputs belong in this hash.  Unsupported decoder controls are
        # rejected before invocation instead of being hashed as if Codex received them.
        "metadata": request.metadata,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
