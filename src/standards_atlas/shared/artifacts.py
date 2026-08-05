"""Consistent filesystem writers for generated text artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

JsonValue = Mapping[str, Any] | Sequence[Any]


def write_text(path: Path, content: str, *, final_newline: bool = False) -> None:
    """Write UTF-8 text after creating the parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if final_newline and not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def write_json(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
    final_newline: bool = True,
) -> None:
    """Serialize and write a JSON artifact with explicit formatting choices."""
    content = json.dumps(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=ensure_ascii,
        default=str,
    )
    write_text(path, content, final_newline=final_newline)


def write_yaml(
    path: Path,
    payload: Any,
    *,
    sort_keys: bool = False,
    allow_unicode: bool = True,
) -> None:
    """Serialize and write a YAML artifact using project-wide defaults."""
    write_text(
        path,
        yaml.safe_dump(payload, sort_keys=sort_keys, allow_unicode=allow_unicode),
    )


def write_markdown(path: Path, content: str) -> None:
    """Write a Markdown artifact as UTF-8 text."""
    write_text(path, content)
