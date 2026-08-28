"""Bounded reader compatibility policy for persisted schema contracts."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SchemaDeprecationWarning(UserWarning):
    """Visible warning emitted when a deprecated persisted schema is read."""


class CompatibilityPhase(StrEnum):
    """Project-wide compatibility phase for schema evolution."""

    REFACTORING = "refactoring"
    STABLE = "stable"


CURRENT_COMPATIBILITY_PHASE = CompatibilityPhase.REFACTORING
STABLE_READER_WINDOW = 3


@dataclass(frozen=True)
class SchemaPolicy:
    """Reader/writer policy for one serialization schema family.

    ``readable`` is the concrete set supported by the current implementation. During
    refactoring it may contain only the current writer schema. Once the project enters
    the stable compatibility phase, schema revisions retain the current version and
    the two immediately preceding *real* predecessor contracts.
    """

    family: str
    current: int | str
    readable: tuple[int | str, ...]
    location: str

    def __post_init__(self) -> None:
        if not self.readable:
            raise ValueError(f"schema policy {self.family!r} must declare readable versions")
        if self.current not in self.readable:
            raise ValueError(
                f"schema policy {self.family!r} must include current version in readable versions"
            )
        if len(self.readable) > STABLE_READER_WINDOW:
            raise ValueError(
                f"schema policy {self.family!r} exceeds the three-version reader window"
            )
        if self.readable[-1] != self.current:
            raise ValueError(f"schema policy {self.family!r} must list the current version last")

    @property
    def deprecated(self) -> tuple[int | str, ...]:
        return tuple(version for version in self.readable if version != self.current)

    def require_readable(self, value: Any) -> None:
        if value not in self.readable:
            supported = ", ".join(repr(version) for version in self.readable)
            raise ValueError(
                f"Unsupported {self.family.replace('-', ' ')} schema version: {value!r}; "
                f"readable versions are {supported}, current is {self.current!r}"
            )
        if value != self.current:
            position = self.readable.index(value)
            oldest = position == 0 and len(self.readable) == STABLE_READER_WINDOW
            suffix = (
                " It is the oldest supported version and will leave the support window "
                "with the next schema revision."
                if oldest
                else " It is deprecated and should no longer be produced."
            )
            warnings.warn(
                f"{self.family} schema version {value!r} is deprecated; "
                f"current is {self.current!r}.{suffix}",
                SchemaDeprecationWarning,
                stacklevel=3,
            )

    def require_current_for_write(self, value: Any) -> None:
        if value != self.current:
            raise ValueError(
                f"{self.family} writers may only emit current schema {self.current!r}; "
                f"got {value!r}"
            )
