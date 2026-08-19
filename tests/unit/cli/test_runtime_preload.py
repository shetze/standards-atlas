from types import SimpleNamespace

from standards_atlas.cli.commands.runtime import _qualification_ramalama_model_refs


def _model(model_ref: str | None, *, provider: str = "ramalama") -> SimpleNamespace:
    return SimpleNamespace(provider=provider, model_ref=model_ref)


def _manifest(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        models=(
            _model("hf.co/example/production-a:Q4_K_M"),
            _model("hf.co/example/shared:Q4_K_M"),
            _model("codex-model", provider="codex"),
        ),
        challenger_qualification=SimpleNamespace(
            enabled=enabled,
            models=(
                _model("hf.co/example/challenger-a:Q4_K_M"),
                _model("hf.co/example/shared:Q4_K_M"),
                _model(None),
            ),
        ),
    )


def test_preload_includes_enabled_challenger_models() -> None:
    refs = _qualification_ramalama_model_refs(_manifest())

    assert refs == (
        "hf.co/example/production-a:Q4_K_M",
        "hf.co/example/shared:Q4_K_M",
        "hf.co/example/challenger-a:Q4_K_M",
    )


def test_preload_ignores_disabled_challenger_models() -> None:
    refs = _qualification_ramalama_model_refs(_manifest(enabled=False))

    assert refs == (
        "hf.co/example/production-a:Q4_K_M",
        "hf.co/example/shared:Q4_K_M",
    )
