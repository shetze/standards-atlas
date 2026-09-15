"""Crash-safe single-state updates and atomic, immutable directory publications."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _preserve_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing history symlink: {path}")
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("stored review history differs from original bytes")
        return
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def output_is_separate(output: Path, inputs: tuple[Path, ...]) -> None:
    for source in inputs:
        source = source.resolve()
        if output == source or (source.is_dir() and output.is_relative_to(source)):
            raise ValueError("review output must be separate from inputs")
    for protected in (
        "data",
        "src/standards_atlas/resources",
        ".atlas/data/documents",
        ".atlas/data/knowledge-evidence",
    ):
        if output.is_relative_to(Path(protected).resolve()):
            raise ValueError("review output must be separate from canonical/public data")


@contextmanager
def review_lock(path: Path):
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "review writer is active; inspect stale lock before manual recovery"
        ) from exc
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_state(root: Path, previous, state) -> None:
    # Called under review_lock; old revisions survive interruption and later corrections.
    if (root / "history").is_symlink():
        raise ValueError("unsafe review history symlink")
    previous_bytes = _json_bytes(previous.model_dump(mode="json"))
    state_payload = state.model_dump(mode="json")
    _preserve_bytes(
        root / "history" / f"{previous.state_sha256}.json",
        previous_bytes,
    )
    _sync_directory(root / "history")
    _atomic_json(root / "review-state.json", state_payload)
    _sync_directory(root)


def new_directory(output: Path, files: dict[str, bytes], *, idempotent: bool = False) -> None:
    """One same-filesystem rename commits both suites and their evidence together."""
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("review output cannot use symlinks")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with review_lock(output.parent / f".{output.name}.review-write.lock"):
        if output.exists():
            actual = {p.relative_to(output).as_posix(): p for p in output.rglob("*") if p.is_file()}
            if (
                idempotent
                and set(actual) == set(files)
                and not any(p.is_symlink() for p in output.rglob("*"))
                and all(actual[k].read_bytes() == value for k, value in files.items())
            ):
                return
            raise ValueError(
                "review output exists; started reviews/publications are never overwritten"
            )
        temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
        try:
            for name, content in files.items():
                path = temporary / name
                if Path(name).is_absolute() or ".." in Path(name).parts:
                    raise ValueError("unsafe review artifact path")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            # Persist staged directory entries before committing their parent name.
            directories = [p for p in temporary.rglob("*") if p.is_dir()]
            for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                _sync_directory(directory)
            _sync_directory(temporary)
            os.rename(temporary, output)
            _sync_directory(output.parent)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
