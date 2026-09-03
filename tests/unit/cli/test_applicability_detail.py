from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.cli.commands.evaluation_commands.applicability_detail import (
    _managed_detail_server,
)


@dataclass(frozen=True)
class _Status:
    running: bool


class _Server:
    def __init__(self, *, running: bool) -> None:
        self.running = running
        self.status_calls = 0
        self.start_calls = 0
        self.stop_calls = 0

    def status(self) -> _Status:
        self.status_calls += 1
        return _Status(self.running)

    def start(self) -> None:
        self.start_calls += 1
        self.running = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.running = False


def test_detail_server_preserves_preexisting_runtime() -> None:
    server = _Server(running=True)

    with _managed_detail_server(server, inference_required=True, enabled=True):
        assert server.running is True

    assert server.status_calls == 1
    assert server.start_calls == 0
    assert server.stop_calls == 0


def test_detail_server_stops_runtime_started_for_invocation() -> None:
    server = _Server(running=False)

    with _managed_detail_server(server, inference_required=True, enabled=True):
        assert server.running is True

    assert server.status_calls == 1
    assert server.start_calls == 1
    assert server.stop_calls == 1
    assert server.running is False


def test_detail_server_is_untouched_without_pending_inference() -> None:
    server = _Server(running=False)

    with _managed_detail_server(server, inference_required=False, enabled=True):
        pass

    assert server.status_calls == 0
    assert server.start_calls == 0
    assert server.stop_calls == 0
