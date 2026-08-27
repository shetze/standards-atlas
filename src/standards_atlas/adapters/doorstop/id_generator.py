"""Generate deterministic Doorstop item identifiers from clause references."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DoorstopIdContext:
    """Configuration for Doorstop item identifier generation.

    Attributes:
        digits:
            Total number of numeric digits in the generated identifier.

        part_shift:
            Numeric offset added to a volume or standard part number.

        part_digits:
            Number of digits reserved for the primary volume or part number.
            If zero, two digits are used when a volume is present.

        volume_depth:
            Optional document-wide number of volume hierarchy components.
            When set, every volume is encoded to exactly this depth, padding
            missing supplement components with zeroes. This prevents a part
            clause from colliding with a supplement clause.
    """

    digits: int
    part_shift: int = 0
    part_digits: int = 0
    volume_depth: int | None = None

    def __post_init__(self) -> None:
        if self.digits < 1:
            raise ValueError("digits must be greater than zero.")

        if self.part_digits < 0:
            raise ValueError("part_digits must not be negative.")

        if self.volume_depth is not None and self.volume_depth < 1:
            raise ValueError("volume_depth must be greater than zero when configured.")


def generate_doorstop_id(
    *,
    visible_reference: str,
    context: DoorstopIdContext,
    volume: str | None = None,
    enum_prefix: str | None = None,
    identifier_width: int | None = None,
) -> str:
    """Generate the numeric part of a Doorstop item identifier."""
    raw_identifier = _raw_doorstop_identifier(
        visible_reference=visible_reference,
        context=context,
        volume=volume,
        enum_prefix=enum_prefix,
        identifier_width=identifier_width,
    )

    if len(raw_identifier) > context.digits:
        raise ValueError(
            f"Generated Doorstop identifier {raw_identifier!r} exceeds "
            f"configured width of {context.digits} digits."
        )

    return raw_identifier.ljust(context.digits, "0")


def required_doorstop_id_width(
    *,
    visible_reference: str,
    context: DoorstopIdContext,
    volume: str | None = None,
    enum_prefix: str | None = None,
    identifier_width: int | None = None,
) -> int:
    """Return the minimum width required for one Doorstop identifier."""
    return len(
        _raw_doorstop_identifier(
            visible_reference=visible_reference,
            context=context,
            volume=volume,
            enum_prefix=enum_prefix,
            identifier_width=identifier_width,
        )
    )


def _raw_doorstop_identifier(
    *,
    visible_reference: str,
    context: DoorstopIdContext,
    volume: str | None,
    enum_prefix: str | None,
    identifier_width: int | None,
) -> str:
    """Build an unpadded numeric Doorstop identifier."""
    if not visible_reference or not visible_reference.strip():
        raise ValueError("visible_reference must not be empty.")

    if identifier_width is not None and identifier_width < 1:
        raise ValueError("identifier_width must be greater than zero.")

    segments = _reference_segments(
        visible_reference=visible_reference.strip(),
        enum_prefix=enum_prefix,
    )
    numeric_parts: list[str] = []

    if volume is not None:
        numeric_parts.append(_format_volume(volume=volume, context=context))

    for index, segment in enumerate(segments):
        is_last_segment = index == len(segments) - 1
        width = identifier_width if is_last_segment and identifier_width is not None else 2
        numeric_parts.append(_format_numeric_segment(segment=segment, width=width))

    return "".join(numeric_parts)


def _reference_segments(
    *,
    visible_reference: str,
    enum_prefix: str | None,
) -> list[str]:
    """Convert a visible clause reference into numeric segment strings.

    Numeric references are returned unchanged.

    Annex references such as ``A`` or ``C.2.4`` are translated into a
    numeric first segment. An explicitly supplied enum prefix takes
    precedence over the implicit annex-letter mapping.
    """
    segments = visible_reference.split(".")

    if any(not segment for segment in segments):
        raise ValueError(f"Invalid clause reference with empty segment: {visible_reference!r}")

    first_segment = segments[0]

    if enum_prefix is not None:
        if not enum_prefix.isdigit():
            raise ValueError(f"enum_prefix must be numeric, got {enum_prefix!r}.")

        return [enum_prefix, *segments[1:]]

    if first_segment.isalpha():
        annex_prefix = _annex_segment_to_numeric(first_segment)

        return [annex_prefix, *segments[1:]]

    return segments


def _annex_segment_to_numeric(segment: str) -> str:
    """Map an alphabetic annex identifier to its numeric representation.

    The mapping starts at 10:

        A -> 10
        B -> 11
        C -> 12

    Multi-letter identifiers use spreadsheet-style alphabetical
    numbering before the offset is applied:

        AA -> 36
        AB -> 37
    """
    normalized = segment.upper()

    if not normalized.isalpha():
        raise ValueError(f"Annex segment must be alphabetic, got {segment!r}.")

    alphabetical_index = 0

    for character in normalized:
        alphabetical_index = alphabetical_index * 26 + ord(character) - ord("A") + 1

    return str(alphabetical_index + 9)


def generate_doorstop_level(
    *,
    visible_reference: str,
    enum_prefix: str | None = None,
) -> str:
    """Generate a numeric hierarchical Doorstop level.

    Numeric clause references remain unchanged.

    Alphabetic annex identifiers are mapped to numeric chapter levels:

        A       -> 10
        A.1     -> 10.1
        C.2.4   -> 12.2.4

    An explicit enum_prefix overrides the default annex mapping.
    """
    if not visible_reference or not visible_reference.strip():
        raise ValueError("visible_reference must not be empty.")

    segments = visible_reference.strip().split(".")

    if any(not segment for segment in segments):
        raise ValueError(f"Invalid clause reference with empty segment: {visible_reference!r}")

    first_segment = segments[0]

    if enum_prefix is not None:
        if not enum_prefix.isdigit():
            raise ValueError(f"enum_prefix must be numeric, got {enum_prefix!r}.")

        level_segments = [enum_prefix, *segments[1:]]
    elif first_segment.isalpha():
        level_segments = [
            _annex_segment_to_numeric(first_segment),
            *segments[1:],
        ]
    else:
        level_segments = segments

    for segment in level_segments:
        if not segment.isdigit():
            raise ValueError(
                "Doorstop level segments must be numeric after annex "
                f"mapping, got {segment!r} in {visible_reference!r}."
            )

    return ".".join(str(int(segment)) for segment in level_segments)


def _format_volume(
    *,
    volume: str,
    context: DoorstopIdContext,
) -> str:
    """Format a standard part and optional supplement hierarchy.

    AtlasData represents supplements with the ``§`` separator. ``3§1`` means
    supplement 1 of part 3. The primary part uses the configured part shift;
    every supplement component is appended as an unshifted two-digit segment.
    This keeps supplement identifiers distinct from ordinary parts such as 31.
    """
    components = volume.split("§")
    if any(not component for component in components):
        raise ValueError(f"Invalid volume hierarchy, got {volume!r}.")

    primary = _format_volume_component(
        component=components[0],
        width=context.part_digits or 2,
        shift=context.part_shift,
        label="Volume",
    )
    supplements = [
        _format_volume_component(
            component=component,
            width=2,
            shift=0,
            label="Supplement",
        )
        for component in components[1:]
    ]

    if context.volume_depth is not None:
        if len(components) > context.volume_depth:
            raise ValueError(
                f"Volume hierarchy {volume!r} exceeds configured depth of {context.volume_depth}."
            )
        supplements.extend("00" for _ in range(context.volume_depth - len(components)))

    return "".join((primary, *supplements))


def _format_volume_component(
    *,
    component: str,
    width: int,
    shift: int,
    label: str,
) -> str:
    """Format one numeric component of a volume hierarchy."""
    try:
        numeric_value = int(component) + shift
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric, got {component!r}.") from exc

    if numeric_value < 0:
        raise ValueError(f"Shifted {label.lower()} must not be negative, got {numeric_value}.")

    if len(str(numeric_value)) > width:
        raise ValueError(f"{label} {numeric_value!r} exceeds configured width of {width} digits.")

    return f"{numeric_value:0{width}d}"


def _format_numeric_segment(
    *,
    segment: str,
    width: int,
) -> str:
    """Format one numeric clause-reference segment."""
    try:
        value = int(segment)
    except ValueError as exc:
        raise ValueError(f"Reference segment must be numeric, got {segment!r}.") from exc

    if value < 0:
        raise ValueError(f"Reference segment must not be negative, got {segment!r}.")

    if len(str(value)) > width:
        raise ValueError(
            f"Reference segment {segment!r} exceeds configured width of {width} digits."
        )

    return f"{value:0{width}d}"
