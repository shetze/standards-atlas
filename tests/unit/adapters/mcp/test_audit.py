import json
from pathlib import Path

from standards_atlas.adapters.mcp.audit import McpAuditLogger


def test_disabled_audit_logger_does_not_create_a_file(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "audit.jsonl"

    McpAuditLogger(path, enabled=False).record("request", method="list_standards")

    assert not path.exists()


def test_audit_logger_creates_parent_and_writes_json_line(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "audit.jsonl"

    McpAuditLogger(path).record(
        "request",
        method="get_clause",
        document_key="ISO26262-2",
        result_count=1,
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "request"
    assert record["method"] == "get_clause"
    assert record["document_key"] == "ISO26262-2"
    assert record["result_count"] == 1
    assert record["timestamp"].endswith("+00:00")


def test_audit_logger_appends_records_and_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = McpAuditLogger(path)

    logger.record("request", query="Überprüfung")
    logger.record("response", status="ok")

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["request", "response"]
    assert records[0]["query"] == "Überprüfung"
