"""Reproduce an untracked context runtime surviving qualification's stop()."""

import json
import subprocess
from dataclasses import replace
from unittest.mock import Mock

import pytest

from standards_atlas.adapters.llm import LlmConfig, RamaLamaServerConfig
from standards_atlas.adapters.llm.ramalama_server import RamaLamaServerError, RamaLamaServerManager
from standards_atlas.application.ports.llm_gateway import LlmHealth


def config(root):
    return LlmConfig(
        server=RamaLamaServerConfig(
            state_directory=root / "runtime",
            ownership_file=root / "active-runtime.json",
            shutdown_timeout_seconds=0.001,
        )
    )


def container(name="standards-atlas-context-enrichment", cid="phi4-id", port=8080):
    return {
        "Id": cid,
        "Name": name,
        "State": {"Running": True},
        "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": str(port)}]}},
    }


class Engine:
    """Minimal Podman contract: reject publish filters, expose actual host bindings."""

    def __init__(self, *containers):
        self.containers = {c["Id"]: c for c in containers}
        self.calls = []
        self.removed = []

    def run(self, command, **_):
        self.calls.append(command)
        _, *args = command
        if any(arg.startswith("publish=") for arg in args):
            return subprocess.CompletedProcess(command, 125, "", "publish is an invalid filter")
        if args[0] == "ps":
            assert args == ["ps", "--format", "{{.ID}}\t{{.Names}}"]
            output = "".join(f"{c['Id']}\t{c['Name']}\n" for c in self.containers.values())
            return subprocess.CompletedProcess(command, 0, output, "")
        if args[:2] == ["container", "inspect"]:
            c = next((c for c in self.containers.values() if args[2] in (c["Id"], c["Name"])), None)
            return subprocess.CompletedProcess(
                command,
                0 if c else 125,
                json.dumps([c]) if c else "",
                "" if c else "no such object",
            )
        if args[:2] == ["rm", "--force"]:
            assert args[2] in self.containers
            self.removed.append(args[2])
            del self.containers[args[2]]
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    def health(self):
        available = any(
            c["State"]["Running"] and c["NetworkSettings"]["Ports"].get("8080/tcp")
            for c in self.containers.values()
        )
        return LlmHealth(available=available, models=("bartowski/phi-4-GGUF",) if available else ())


def install(monkeypatch, engine):
    monkeypatch.setattr("subprocess.run", engine.run)
    monkeypatch.setattr(
        "standards_atlas.adapters.llm.ramalama_server.OpenAICompatibleLlmGateway.health",
        engine.health,
    )


def test_missing_ownership_handoff_and_idempotent_stop(tmp_path, monkeypatch):
    engine = Engine(container())
    install(monkeypatch, engine)
    manager = RamaLamaServerManager(config(tmp_path))
    manager.stop()
    manager.stop()
    assert engine.removed == ["phi4-id"]
    assert not any("publish=" in str(call) for call in engine.calls)


def test_stale_missing_container_receipt_falls_back_to_actual_runtime(tmp_path, monkeypatch):
    engine = Engine(container())
    install(monkeypatch, engine)
    cfg = config(tmp_path)
    cfg.server.ownership_file.write_text(
        json.dumps(
            {
                "container_id": "old-id",
                "container_name": "standards-atlas-llm",
                "port": 8080,
            }
        )
    )
    RamaLamaServerManager(cfg).stop()
    assert engine.removed == ["phi4-id"]
    assert not cfg.server.ownership_file.exists()


def test_same_model_reuse_restores_shared_ownership(tmp_path, monkeypatch):
    engine = Engine(container())
    install(monkeypatch, engine)
    cfg = config(tmp_path)
    cfg = replace(cfg, server=replace(cfg.server, model="hf.co/bartowski/phi-4-GGUF:Q4_K_M"))
    RamaLamaServerManager(cfg).start()
    receipt = json.loads(cfg.server.ownership_file.read_text())
    assert receipt["container_name"] == "standards-atlas-context-enrichment"
    assert receipt["container_id"] == "phi4-id"
    assert engine.removed == []
    RamaLamaServerManager(config(tmp_path)).stop()
    assert engine.removed == ["phi4-id"]


def test_list_errors_are_not_interpreted_as_empty_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        Mock(
            return_value=subprocess.CompletedProcess(
                (),
                125,
                "",
                "permission denied",
            )
        ),
    )
    with pytest.raises(RamaLamaServerError, match="Could not list.*permission denied"):
        RamaLamaServerManager(config(tmp_path)).stop()


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("podman"), subprocess.TimeoutExpired("ps", 10)],
)
def test_query_launch_errors_are_visible(tmp_path, monkeypatch, error):
    monkeypatch.setattr("subprocess.run", Mock(side_effect=error))
    with pytest.raises(RamaLamaServerError, match="query container engine"):
        RamaLamaServerManager(config(tmp_path)).stop()


@pytest.mark.parametrize("name", ["unrelated-llm", "standards-atlas-context-enrichment"])
def test_foreign_and_other_port_containers_are_never_removed(tmp_path, monkeypatch, name):
    c = container(name=name, port=9090 if name.startswith("standards") else 8080)
    engine = Engine(c)
    install(monkeypatch, engine)
    manager = RamaLamaServerManager(config(tmp_path))
    monkeypatch.setattr(manager, "_wait_for_endpoint_shutdown", Mock())
    manager.stop()
    assert engine.removed == []


def test_foreign_endpoint_still_blocks_switch_and_keeps_receipt(tmp_path, monkeypatch):
    engine = Engine(container(name="foreign"))
    install(monkeypatch, engine)
    cfg = config(tmp_path)
    original = json.dumps({"container_id": "old", "container_name": "old", "port": 8080})
    cfg.server.ownership_file.write_text(original)
    with pytest.raises(RamaLamaServerError, match="remained available.*No foreign"):
        RamaLamaServerManager(cfg).stop()
    assert engine.removed == []
    assert cfg.server.ownership_file.read_text() == original


def test_other_port_ownership_and_live_named_container_are_preserved(tmp_path, monkeypatch):
    engine = Engine(container(name="standards-atlas-llm", port=9090))
    install(monkeypatch, engine)
    cfg = config(tmp_path)
    original = json.dumps(
        {
            "container_id": "phi4-id",
            "container_name": "standards-atlas-llm",
            "port": 9090,
        }
    )
    cfg.server.ownership_file.write_text(original)
    manager = RamaLamaServerManager(cfg)
    monkeypatch.setattr(manager, "_wait_for_endpoint_shutdown", Mock())
    manager.stop()
    assert engine.removed == []
    assert cfg.server.ownership_file.read_text() == original


def test_ambiguous_project_endpoints_are_not_stopped(tmp_path, monkeypatch):
    engine = Engine(container(), container(name="standards-atlas-other", cid="other-id"))
    install(monkeypatch, engine)
    with pytest.raises(RamaLamaServerError, match="Multiple project-owned"):
        RamaLamaServerManager(config(tmp_path)).stop()
    assert engine.removed == []


@pytest.mark.parametrize("payload", ["{}", "[]", "not json"])
def test_malformed_inspect_output_is_rejected(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(
        "subprocess.run",
        Mock(
            return_value=subprocess.CompletedProcess(
                (),
                0,
                payload,
                "",
            )
        ),
    )
    with pytest.raises(RamaLamaServerError, match="Invalid container inspection"):
        RamaLamaServerManager(config(tmp_path))._inspect_container("id")


@pytest.mark.parametrize(
    "ports",
    [
        {"8080/tcp": None},
        {"8080/udp": [{"HostPort": "8080"}]},
        {"8080/tcp": [{"HostPort": "18080"}]},
        {"8080/tcp": [{"HostPort": "8080", "HostIp": "192.0.2.1"}]},
    ],
)
def test_exposed_udp_and_other_host_ports_are_not_endpoint_identity(tmp_path, monkeypatch, ports):
    c = container()
    c["NetworkSettings"]["Ports"] = ports
    engine = Engine(c)
    install(monkeypatch, engine)
    assert RamaLamaServerManager(config(tmp_path))._containers_publishing_port(8080) == ()


def test_host_network_requires_explicit_server_command_port(tmp_path, monkeypatch):
    c = container()
    c["NetworkSettings"] = {}
    c["HostConfig"] = {"NetworkMode": "host"}
    c["Path"] = "/usr/bin/llama-server"
    c["Args"] = ["--port", "8080"]
    engine = Engine(c)
    install(monkeypatch, engine)
    manager = RamaLamaServerManager(config(tmp_path))
    assert manager._containers_publishing_port(8080) == (("phi4-id", c["Name"]),)
    c["Args"] = ["--port", "9090"]
    assert manager._containers_publishing_port(8080) == ()


def test_engine_selection_is_respected_without_docker_only_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMALAMA_CONTAINER_ENGINE", "docker")
    engine = Engine(container())
    install(monkeypatch, engine)
    RamaLamaServerManager(config(tmp_path)).stop()
    assert all(call[0] == "docker" for call in engine.calls)
