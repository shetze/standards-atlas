from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/fixtures/ap02/context-evidence-inspection"


def _run(output: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), env.get("PYTHONPATH", ""))).rstrip(
        os.pathsep
    )
    for name in tuple(env):
        upper = name.upper()
        if any(token in upper for token in ("OPENAI", "RAMALAMA", "LLM_API", "ANTHROPIC")):
            env.pop(name, None)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from standards_atlas.cli import app; app()",
            "context",
            "evidence-inspect",
            "--workspace",
            str(FIXTURE / "workspace"),
            "--document-key",
            "AP02-SYNTH",
            "--clause-id",
            "target",
            "--grounding-requests",
            str(FIXTURE / "grounding-requests.json"),
            "--character-budget",
            "20000",
            "--max-sequence-distance",
            "8",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def test_model_free_inspection_cli_is_deterministic_across_fresh_processes(tmp_path: Path) -> None:
    first = tmp_path / "inspection-1.json"
    second = tmp_path / "inspection-2.json"

    first_run = _run(first)
    second_run = _run(second)

    assert first_run.returncode == 0, first_run.stdout + first_run.stderr
    assert second_run.returncode == 0, second_run.stdout + second_run.stderr
    assert first.read_bytes() == second.read_bytes()
    assert "Model execution           : no" in first_run.stdout
    assert "Semantic quality assessed : no" in first_run.stdout

    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["model_execution"] is False
    assert payload["semantic_quality_assessed"] is False
    assert payload["selection_completeness"] == "bounded"
    assert len(payload["selected_sources"]) == 7
    assert len(payload["omitted_sources"]) == 1
    assert len(payload["grounding_results"]) == 3
    assert [item["complete"] for item in payload["grounding_results"]] == [True, True, False]
    assert payload["grounding_results"][2]["failures"][0]["code"] == "quote_not_found"

    stored = first.read_text(encoding="utf-8")
    assert "The evaluation shall assess" not in stored
    assert "Safety plan confirmation review" not in stored
    assert "text deliberately absent" not in stored
