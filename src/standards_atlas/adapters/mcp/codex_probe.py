"""Explicit Codex-client MCP probe using only the text-free ``get_server_info`` tool."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.adapters.mcp.codex import CodexMcpConfig


@dataclass(frozen=True)
class CodexClientProbeReport:
    status: str
    executable: str
    client_version: str | None = None
    model: str | None = None
    tool_read: bool | None = None
    mcp_profile: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "executable": self.executable,
            "client_version": self.client_version,
            "model": self.model,
            "tool_read": self.tool_read,
            "mcp_profile": self.mcp_profile,
            "detail": self.detail,
            "data_scope": "synthetic-text-free-server-info",
            "real_norm_text_used": False,
        }


class CodexClientMcpProbe:
    """Check the actual Codex binary and, only with opt-in, one safe MCP tool read."""

    def __init__(self, executable: str = "codex") -> None:
        self._executable = executable

    def run(
        self,
        *,
        url: str,
        server_name: str,
        token_environment_variable: str,
        allow_synthetic_model_call: bool,
        model: str | None,
        timeout_seconds: int = 120,
    ) -> CodexClientProbeReport:
        executable = shutil.which(self._executable)
        if executable is None:
            return CodexClientProbeReport(
                status="not_executed",
                executable=self._executable,
                detail="Codex executable is not available in PATH",
            )
        try:
            version_run = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return CodexClientProbeReport(
                status="failed",
                executable=executable,
                detail=f"Codex version probe failed: {exc}",
            )
        version = (version_run.stdout or version_run.stderr).strip() or None
        if version_run.returncode != 0:
            return CodexClientProbeReport(
                status="failed",
                executable=executable,
                client_version=version,
                detail="Codex version command returned a non-zero status",
            )
        if not allow_synthetic_model_call:
            return CodexClientProbeReport(
                status="not_executed",
                executable=executable,
                client_version=version,
                detail="real client tool read requires --allow-synthetic-model-call",
            )
        if not model:
            return CodexClientProbeReport(
                status="not_executed",
                executable=executable,
                client_version=version,
                detail="real client tool read requires an explicit --model",
            )

        client_config = CodexMcpConfig(
            url=url,
            server_name=server_name,
            bearer_token_env_var=token_environment_variable,
            enabled_tools=("get_server_info",),
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["client_tool_read", "mcp_profile"],
            "properties": {
                "client_tool_read": {"type": "boolean"},
                "mcp_profile": {"type": ["string", "null"]},
            },
        }
        prompt = (
            "Use only the MCP tool get_server_info from the configured Standards Atlas server. "
            "Do not call shell commands, files, search, clause, review, experiment, "
            "or other tools. "
            "Return client_tool_read=true only if the tool call succeeded, and copy mcp_profile "
            "from that tool result. This probe intentionally uses no standards text."
        )
        with tempfile.TemporaryDirectory(prefix="standards-atlas-codex-probe-") as directory:
            root = Path(directory)
            (root / "config.toml").write_text(client_config.render_toml(), encoding="utf-8")
            schema_path = root / "schema.json"
            output_path = root / "result.json"
            schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
            environment = dict(os.environ)
            environment["CODEX_HOME"] = str(root)
            command = [
                executable,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--model",
                model,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            try:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                    env=environment,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                return CodexClientProbeReport(
                    status="failed",
                    executable=executable,
                    client_version=version,
                    model=model,
                    detail=f"Codex client tool probe failed: {exc}",
                )
            if completed.returncode != 0 or not output_path.is_file():
                detail = (completed.stderr or completed.stdout).strip()
                return CodexClientProbeReport(
                    status="failed",
                    executable=executable,
                    client_version=version,
                    model=model,
                    detail=detail or f"Codex exited with {completed.returncode}",
                )
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return CodexClientProbeReport(
                    status="failed",
                    executable=executable,
                    client_version=version,
                    model=model,
                    detail=f"Codex probe result was not valid JSON: {exc}",
                )
            tool_read = payload.get("client_tool_read") is True
            profile = payload.get("mcp_profile")
            return CodexClientProbeReport(
                status="passed" if tool_read else "failed",
                executable=executable,
                client_version=version,
                model=model,
                tool_read=tool_read,
                mcp_profile=profile if isinstance(profile, str) else None,
                detail=(
                    None if tool_read else "Codex did not confirm the MCP get_server_info tool read"
                ),
            )
