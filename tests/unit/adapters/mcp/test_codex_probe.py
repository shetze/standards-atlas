import json
import subprocess
from pathlib import Path

from standards_atlas.adapters.mcp.codex_probe import CodexClientMcpProbe


def test_missing_codex_client_is_reported_as_not_executed() -> None:
    report = CodexClientMcpProbe("definitely-not-installed-codex").run(
        url="http://127.0.0.1:8765/mcp",
        server_name="standards-atlas",
        token_environment_variable="STANDARDS_ATLAS_MCP_TOKEN",
        allow_synthetic_model_call=False,
        model=None,
    )

    assert report.status == "not_executed"
    assert report.tool_read is None
    assert report.as_dict()["real_norm_text_used"] is False


def test_real_probe_preserves_existing_codex_auth_without_loading_user_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    auth_path = codex_home / "auth.json"
    auth_path.write_text('{"auth_mode":"chatgpt","secret":"do-not-copy"}\n', encoding="utf-8")
    (codex_home / "config.toml").write_text(
        '[mcp_servers.unrelated]\nurl = "https://unrelated.example/mcp"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(
        "standards_atlas.adapters.mcp.codex_probe.shutil.which",
        lambda _: "/usr/local/bin/codex",
    )

    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((list(command), dict(kwargs)))
        if command == ["/usr/local/bin/codex", "--version"]:
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.160.0\n", "")

        environment = kwargs["env"]
        probe_home = Path(environment["CODEX_HOME"])
        assert probe_home.parent == codex_home
        probe_auth = probe_home / "auth.json"
        assert probe_auth.is_symlink()
        assert probe_auth.resolve() == auth_path.resolve()
        assert probe_auth.read_text(encoding="utf-8") == auth_path.read_text(encoding="utf-8")

        probe_config = (probe_home / "config.toml").read_text(encoding="utf-8")
        assert "get_server_info" in probe_config
        assert "unrelated.example" not in probe_config
        assert "do-not-copy" not in probe_config
        assert kwargs["cwd"] == probe_home / "workspace"
        assert Path(kwargs["cwd"]).is_dir()

        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(
            json.dumps(
                {
                    "client_tool_read": True,
                    "mcp_profile": "ap03-development",
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "standards_atlas.adapters.mcp.codex_probe.subprocess.run",
        fake_run,
    )

    report = CodexClientMcpProbe().run(
        url="http://127.0.0.1:8765/mcp",
        server_name="standards-atlas-ap03-development",
        token_environment_variable="STANDARDS_ATLAS_MCP_TOKEN",
        allow_synthetic_model_call=True,
        model="gpt-6-astra",
    )

    assert report.status == "passed"
    assert report.client_version == "codex-cli 0.160.0"
    assert report.tool_read is True
    assert report.mcp_profile == "ap03-development"
    assert len(calls) == 2
