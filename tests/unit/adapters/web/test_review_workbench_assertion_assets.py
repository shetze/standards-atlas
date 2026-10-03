from __future__ import annotations

from pathlib import Path

import standards_atlas


def _workbench_root() -> Path:
    package_root = Path(standards_atlas.__file__).resolve().parent
    return package_root / "resources" / "web" / "review_workbench"


def test_assertion_review_emphasizes_partition_guidance_and_target_source() -> None:
    root = _workbench_root()
    javascript = (root / "app.js").read_text(encoding="utf-8")
    css = (root / "app.css").read_text(encoding="utf-8")

    assert "assertion-key-badge" in javascript
    assert "assertion-guidance" in javascript
    assert "Target clause · immediate review basis" in javascript
    assert 'element("p","Target heading","assertion-target-field-label")' in javascript
    assert (
        'element("p","Target body","assertion-target-field-label assertion-target-body-label")'
        in javascript
    )
    assert "assertion-target-heading" in javascript
    assert "assertion-target-body" in javascript
    assert ".assertion-key-badge" in css
    assert ".assertion-guidance" in css
    assert ".assertion-target-field-label" in css
    assert ".assertion-target-heading" in css
    assert ".assertion-target-body" in css


def test_review_workbench_defaults_to_english_without_adding_i18n_runtime() -> None:
    root = _workbench_root()
    html = (root / "index.html").read_text(encoding="utf-8")
    javascript = (root / "app.js").read_text(encoding="utf-8")
    formatting = (root / "format.js").read_text(encoding="utf-8")

    assert '<html lang="en">' in html
    assert "Open / resume package" in html
    assert "Source &amp; structure" in html
    assert "Proposal ≠ confirmation" in html
    assert "Review the source first." in javascript
    assert "No model proposal available" in javascript
    assert 'Intl.DateTimeFormat("en-GB"' in formatting
