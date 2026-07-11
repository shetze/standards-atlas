"""Round-trip writer for legacy AtlasData files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from standards_atlas.adapters.atlasdata.parser import (
    InitializationRecord,
    parse_initialization_records,
)
from standards_atlas.adapters.atlasdata.toc_generator import (
    generate_public_initialization_records,
)
from standards_atlas.domain.model import EngineeringDocument


DATA_MARKER = "#---data---#"


@dataclass(frozen=True)
class AtlasDataRoundTripResult:
    """Result of an AtlasData round-trip update."""

    source: Path
    backup: Path | None
    generated_toc_records: int
    preserved_toc_headings: int
    preserved_public_text_records: int
    removed_records: int
    changed: bool

class AtlasDataRoundTripWriter:
    """Update the generated TOC section of an AtlasData file safely."""

    def update_toc(
        self,
        source: Path,
        document: EngineeringDocument,
        *,
        write: bool = False,
    ) -> AtlasDataRoundTripResult:
        original_text = source.read_text(encoding="utf-8")
        existing_records = parse_initialization_records(original_text)

        generated_records = generate_public_initialization_records(document)
        _validate_public_records(generated_records)

        (
            updated_records,
            preserved_toc_headings,
            preserved_public_text_records,
        ) = self._merge_records(
            generated_records=generated_records,
            existing_records=existing_records,
        )

        updated_text = self._replace_data_section(
            original_text=original_text,
            records=updated_records,
        )

        changed = updated_text != original_text
        backup: Path | None = None

        if write and changed:
            backup = self._create_numbered_backup(source)
            source.write_text(updated_text, encoding="utf-8")

        existing_keys = {
            (record.kind, record.reference)
            for record in updated_records
        }

        removed_records = sum(
            (record.kind, record.reference) not in existing_keys
            for record in existing_records
        )

        generated_toc_records = sum(
            record.kind == "TOC"
            for record in generated_records
        )

        return AtlasDataRoundTripResult(
            source=source,
            backup=backup,
            generated_toc_records=generated_toc_records,
            preserved_toc_headings=preserved_toc_headings,
            preserved_public_text_records=preserved_public_text_records,
            removed_records=removed_records,
            changed=changed,
        )

    def _merge_records(
        self,
        *,
        generated_records: list[InitializationRecord],
        existing_records: list[InitializationRecord],
    ) -> tuple[list[InitializationRecord], int, int]:
        existing_toc = {
            record.reference: record
            for record in existing_records
            if record.kind == "TOC"
        }

        preserved_headings = 0
        merged: list[InitializationRecord] = []

        for generated in generated_records:
            if generated.kind != "TOC":
                merged.append(generated)
                continue

            existing = existing_toc.get(generated.reference)

            if existing and existing.content.strip():
                preserved_headings += 1
                merged.append(
                    InitializationRecord(
                        kind="TOC",
                        hash_value=generated.hash_value,
                        reference=generated.reference,
                        content=existing.content,
                        type_marker=generated.type_marker,
                    )
                )
            else:
                merged.append(generated)

        public_text_count = sum(
            record.kind == "PublicTXT"
            for record in merged
        )

        return merged, preserved_headings, public_text_count

    def _replace_data_section(
        self,
        *,
        original_text: str,
        records: list[InitializationRecord],
    ) -> str:
        rendered_records = "\n".join(
            _render_record(record)
            for record in records
        )

        if DATA_MARKER in original_text:
            head, _ = original_text.split(DATA_MARKER, 1)
            return f"{head.rstrip()}\n\n{DATA_MARKER}\n{rendered_records}\n"

        return (
            f"{original_text.rstrip()}\n\n"
            f"{DATA_MARKER}\n"
            f"{rendered_records}\n"
        )

    def _create_numbered_backup(self, source: Path) -> Path:
        counter = 1

        while True:
            backup = source.with_name(f"{source.name}.bak.{counter}")

            if not backup.exists():
                shutil.copy2(source, backup)
                return backup

            counter += 1


def _validate_public_records(
    records: list[InitializationRecord],
) -> None:
    forbidden = [
        record.kind
        for record in records
        if record.kind not in {"TOC", "PublicTXT"}
    ]

    if forbidden:
        raise ValueError(
            "Round-trip writer received non-public record kinds: "
            f"{forbidden}"
        )


def _render_record(record: InitializationRecord) -> str:
    return (
        f"{record.kind};"
        f"{record.hash_value};"
        f"{record.reference};"
        f"{record.content};"
        f"{record.type_marker}"
    )
