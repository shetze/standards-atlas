from pathlib import Path

from standards_atlas.application.workspace import WorkspaceLayout


def test_workspace_layout_separates_lifecycle_classes(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)

    assert layout.data == tmp_path / ".atlas" / "data"
    assert layout.cache == tmp_path / ".atlas" / "cache"
    assert layout.work == tmp_path / ".atlas" / "work"
    assert layout.review == tmp_path / "local" / "review"
    assert layout.evaluation_corpora == tmp_path / ".atlas" / "data" / "evaluation" / "corpora"


def test_clear_work_never_removes_data_cache_or_local(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    work = layout.work / "workflow" / "debug.txt"
    data = layout.data / "documents" / "DOC.json"
    cache = layout.cache / "llm" / "response.json"
    review = layout.review / "qualification" / "review.md"
    for path in (work, data, cache, review):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep\n", encoding="utf-8")

    layout.clear_work()

    assert not layout.work.exists()
    assert data.exists()
    assert cache.exists()
    assert review.exists()


def test_clear_work_can_preserve_workflow_checkpoints(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    checkpoint = layout.work / "workflow" / "semantic" / "DOC.complete"
    scratch = layout.work / "doorstop" / "tmp.txt"
    for path in (checkpoint, scratch):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("state\n", encoding="utf-8")

    layout.clear_work(preserve_workflow=True)

    assert checkpoint.exists()
    assert not scratch.exists()
