from standards_atlas.application.semantic_qualification.proposals import ProposalProgress
from standards_atlas.cli.commands.evaluation import _format_duration, _MatrixProposalProgress


def _progress(*, current: int, total: int, status: str) -> ProposalProgress:
    return ProposalProgress(
        current=current,
        total=total,
        example_id=f"clause-{current}",
        status=status,
        document_key="ISO26262-11",
        reference="4.6.2.1.1.2",
        title="Temperature de-rating",
    )


def test_format_duration() -> None:
    assert _format_duration(0) == "00:00"
    assert _format_duration(65) == "01:05"
    assert _format_duration(3661) == "01:01:01"


def test_matrix_progress_updates_one_line(monkeypatch) -> None:
    output: list[tuple[str, bool]] = []

    def capture(message: str, *, nl: bool = True, **_: object) -> None:
        output.append((message, nl))

    monkeypatch.setattr("standards_atlas.cli.commands.evaluation.typer.echo", capture)
    reporter = _MatrixProposalProgress(
        candidate_index=1,
        candidate_total=48,
        label="qwen3-14b-q4-k-m / content-only / disabled / repeat 1",
    )

    reporter(_progress(current=1, total=500, status="processing"))
    reporter(_progress(current=1, total=500, status="generated"))
    reporter.finish(generated=1, failed=0, skipped=0)

    assert output[0][0].startswith(
        "\r[Candidate 01/48] qwen3-14b-q4-k-m / content-only / disabled / repeat 1 [001/500]"
    )
    assert output[0][1] is False
    assert "ok=1 failed=0" in output[1][0]
    assert "complete: ok=1 failed=0 skipped=0" in output[2][0]
    assert output[2][1] is True
