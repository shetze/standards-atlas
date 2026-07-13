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
            Number of digits reserved for the volume or part number.
            If zero, two digits are used when a volume is present.
    """

    digits: int
    part_shift: int = 0
    part_digits: int = 0

    def __post_init__(self) -> None:
        if self.digits < 1:
            raise ValueError("digits must be greater than zero.")

        if self.part_digits < 0:
            raise ValueError("part_digits must not be negative.")


def generate_doorstop_id(
    *,
    visible_reference: str,
    context: DoorstopIdContext,
    volume: str | None = None,
    enum_prefix: str | None = None,
    identifier_width: int | None = None,
) -> str:
    """Generate the numeric part of a Doorstop item identifier.

    The generated identifier contains only digits. The Doorstop document
    prefix and separator are added by the Doorstop exporter.

    Examples:
        5.1.2 with digits=8:
            05010200

        11.4.7.1 with volume=8 and digits=10:
            0811040701

        C.2.4.1 with enum_prefix=12 and digits=8:
            12020401

    Args:
        visible_reference:
            Human-readable clause reference, such as ``5.1.2`` or
            ``C.2.4.1``.

        context:
            Document-wide identifier generation configuration.

        volume:
            Optional volume or standard part identifier.

        enum_prefix:
            Numeric replacement for a non-numeric first reference segment,
            typically used for annexes.

        identifier_width:
            Optional width for the final reference segment. This supports
            AtlasData structures using the ``.+`` marker for three-digit
            sequence numbers.

    Returns:
        A zero-padded numeric Doorstop identifier.

    Raises:
        ValueError:
            If the reference cannot be converted into numeric segments or
            the resulting identifier exceeds the configured width.
    """
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
        numeric_parts.append(
            _format_volume(
                volume=volume,
                context=context,
            )
        )

    for index, segment in enumerate(segments):
        is_last_segment = index == len(segments) - 1

        width = identifier_width if is_last_segment and identifier_width is not None else 2

        numeric_parts.append(
            _format_numeric_segment(
                segment=segment,
                width=width,
            )
        )

    raw_identifier = "".join(numeric_parts)

    if len(raw_identifier) > context.digits:
        raise ValueError(
            f"Generated Doorstop identifier {raw_identifier!r} exceeds "
            f"configured width of {context.digits} digits."
        )

    return raw_identifier.ljust(context.digits, "0")


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
    """Format the optional document volume or standard part."""
    try:
        numeric_volume = int(volume) + context.part_shift
    except ValueError as exc:
        raise ValueError(f"Volume must be numeric, got {volume!r}.") from exc

    if numeric_volume < 0:
        raise ValueError(f"Shifted volume must not be negative, got {numeric_volume}.")

    width = context.part_digits or 2

    if len(str(numeric_volume)) > width:
        raise ValueError(f"Volume {numeric_volume!r} exceeds configured width of {width} digits.")

    return f"{numeric_volume:0{width}d}"


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
