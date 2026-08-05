from __future__ import annotations

import json
from pathlib import Path

import yaml

from standards_atlas.shared.artifacts import write_json, write_markdown, write_text, write_yaml


def test_writers_create_parent_directories_and_preserve_expected_formats(tmp_path: Path) -> None:
    text = tmp_path / "nested" / "plain.txt"
    json_path = tmp_path / "nested" / "value.json"
    yaml_path = tmp_path / "nested" / "value.yaml"
    markdown = tmp_path / "nested" / "value.md"

    write_text(text, "plain", final_newline=True)
    write_json(json_path, {"name": "Ä", "value": 1})
    write_yaml(yaml_path, {"name": "Ä", "value": 1})
    write_markdown(markdown, "# Title\n")

    assert text.read_text(encoding="utf-8") == "plain\n"
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"name": "Ä", "value": 1}
    assert json_path.read_text(encoding="utf-8").endswith("\n")
    assert yaml.safe_load(yaml_path.read_text(encoding="utf-8")) == {"name": "Ä", "value": 1}
    assert markdown.read_text(encoding="utf-8") == "# Title\n"
