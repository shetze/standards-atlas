from __future__ import annotations

from pathlib import Path

import standards_atlas


def test_assertion_review_emphasizes_partition_guidance_and_target_source() -> None:
    package_root = Path(standards_atlas.__file__).resolve().parent
    root = package_root / "resources" / "web" / "review_workbench"
    javascript = (root / "app.js").read_text(encoding="utf-8")
    css = (root / "app.css").read_text(encoding="utf-8")

    assert "assertion-key-badge" in javascript
    assert "assertion-guidance" in javascript
    assert "Zielklausel · unmittelbare Reviewgrundlage" in javascript
    assert "assertion-target-heading" in javascript
    assert "assertion-target-body" in javascript
    assert ".assertion-key-badge" in css
    assert ".assertion-guidance" in css
    assert ".assertion-target-heading" in css
    assert ".assertion-target-body" in css
