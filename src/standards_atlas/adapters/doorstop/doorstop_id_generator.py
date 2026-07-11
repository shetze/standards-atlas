"""Doorstop AtlasData numeric identifier generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DoorstopIdGenerationContext:
    """Configuration used for doorstop AtlasData numeric IDs."""

    digits: int
    part_shift: int = 0
    part_digits: int = 0


def generate_doorstop_num_id(
    *,
    visible_reference: str,
    context: DoorstopIdGenerationContext,
    volume: str | None = None,
    enum_prefix: str | None = None,
    identifier_width: int | None = None,
) -> str:
    """Generate the doorstop numeric AtlasData identifier.

    Examples:
        5.1.2 with digits=8 -> 05010200
        11.4.7.1 with volume=8, part_digits=2 -> 0811040701

    The enum_prefix is used for annex-like references where the visible
    reference is non-numeric, for example A or C.2.4.
    """
    segments = _reference_segments(
        visible_reference=visible_reference,
        enum_prefix=enum_prefix,
    )

    numeric_parts: list[str] = []

    if volume is not None:
        numeric_parts.append(_format_volume(volume, context))

    for index, segment in enumerate(segments):
        width = identifier_width if index == len(segments) - 1 and identifier_width else 2
        numeric_parts.append(_format_numeric_segment(segment, width=width))

    raw = "".join(numeric_parts)

    if len(raw) > context.digits:
        raise ValueError(
            f"Generated doorstop id {raw!r} exceeds configured width "
            f"of {context.digits} digits."
        )

    return raw.ljust(context.digits, "0")


def _reference_segments(
    *,
    visible_reference: str,
    enum_prefix: str | None,
) -> list[str]:
    if enum_prefix is not None:
        remainder = visible_reference.split(".", 1)

        if len(remainder) == 1:
            return [enum_prefix]

        return [enum_prefix, *remainder[1].split(".")]

    return visible_reference.split(".")


def _format_volume(
    volume: str,
    context: DoorstopIdGenerationContext,
) -> str:
    try:
        numeric_volume = int(volume) + context.part_shift
    except ValueError as exc:
        raise ValueError(f"Volume must be numeric, got {volume!r}.") from exc

    width = context.part_digits or 2
    return f"{numeric_volume:0{width}d}"


def _format_numeric_segment(segment: str, *, width: int) -> str:
    try:
        value = int(segment)
    except ValueError as exc:
        raise ValueError(f"Reference segment must be numeric, got {segment!r}.") from exc

    return f"{value:0{width}d}"
