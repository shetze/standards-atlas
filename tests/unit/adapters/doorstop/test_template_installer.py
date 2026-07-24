from __future__ import annotations

from pathlib import Path

import pytest

from standards_atlas.adapters.doorstop import DoorstopTemplateInstaller


def _document(root: Path, name: str, *, parent: str | None = None) -> Path:
    document = root / name
    document.mkdir(parents=True)
    parent_line = f"  parent: {parent}\n" if parent else ""
    (document / ".doorstop.yml").write_text(
        "settings:\n" + parent_line + f"  prefix: {name}\n  digits: 3\n  sep: ''\n",
        encoding="utf-8",
    )
    return document


@pytest.mark.parametrize(
    "template_name",
    ("atlas-clean", "technical-blueprint", "midnight-focus"),
)
def test_installs_packaged_template_beside_root_document(
    tmp_path: Path, template_name: str
) -> None:
    root_document = _document(tmp_path, "ROOT")
    _document(tmp_path, "CHILD", parent="ROOT")

    installed = DoorstopTemplateInstaller().install(tmp_path, template_name)

    assert installed == root_document / "template"
    assert (installed / "views" / "doorstop.tpl").is_file()
    assert (installed / "doorstop.css").is_file()
    assert (installed / "doorstop.js").is_file()
    assert "atlas-sidebar" in (installed / "views" / "doorstop.tpl").read_text(
        encoding="utf-8"
    )
    assert "atlasToc" in (installed / "doorstop.js").read_text(encoding="utf-8")


def test_rejects_unknown_template(tmp_path: Path) -> None:
    _document(tmp_path, "ROOT")

    with pytest.raises(ValueError, match="unknown Doorstop template"):
        DoorstopTemplateInstaller().install(tmp_path, "unknown")


def test_requires_exactly_one_root_document(tmp_path: Path) -> None:
    _document(tmp_path, "ROOT-A")
    _document(tmp_path, "ROOT-B")

    with pytest.raises(ValueError, match="exactly one root"):
        DoorstopTemplateInstaller().install(tmp_path, "atlas-clean")
