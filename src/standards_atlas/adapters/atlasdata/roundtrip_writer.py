"""Round-trip writer for legacy AtlasData files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from standards_atlas.adapters.atlasdata.parser import (
    InitializationRecord,
    parse_initialization_records,
)
from standards_atlas.adapters.atlasdata.toc_generator import generate_toc_records
from standards_atlas.domain.model import EngineeringDocument


DATA_MARKER = "#---data---#"


@dataclass(frozen=True)
class AtlasDataRoundTripResult:
    """Result of an AtlasData round-trip update."""

    source: Path
    backup: Path | None
    generated_toc_records: int
    preserved_toc_headings: int
    preserved_text_records: int
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
        """Generate and optionally write an updated TOC section.

        When write=True, a numbered backup of the original file is created
        before modifying the source file.
        """
        original_text = source.read_text(encoding="utf-8")
        existing_records = parse_initialization_records(original_text)

        generated_toc = generate_toc_records(document)
        updated_records, preserved_toc_headings = self._merge_records(
            generated_toc=generated_toc,
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

        existing_references = {record.reference for record in updated_records}
        removed_records = len(
            [
                record
                for record in existing_records
                if record.reference not in existing_references
            ]
        )

        preserved_text_records = len(
            [record for record in updated_records if record.kind == "TEXT"]
        )

        return AtlasDataRoundTripResult(
            source=source,
            backup=backup,
            generated_toc_records=len(generated_toc),
            preserved_toc_headings=preserved_toc_headings,
            preserved_text_records=preserved_text_records,
            removed_records=removed_records,
            changed=changed,
        )

    def _merge_records(
        self,
        *,
        generated_toc: list[InitializationRecord],
        existing_records: list[InitializationRecord],
    ) -> tuple[list[InitializationRecord], int]:
        existing_by_reference = {
            record.reference: record
            for record in existing_records
            if record.kind == "TOC"
        }

        valid_references = {record.reference for record in generated_toc}

        preserved_toc_headings = 0
        merged_records: list[InitializationRecord] = []

        for generated in generated_toc:
            existing = existing_by_reference.get(generated.reference)

            if existing and existing.content:
                preserved_toc_headings += 1
                merged_records.append(
                    InitializationRecord(
                        kind=generated.kind,
                        hash_value=generated.hash_value,
                        reference=generated.reference,
                        content=existing.content,
                        type_marker=existing.type_marker,
                    )
                )
            else:
                merged_records.append(generated)

        for existing in existing_records:
            if existing.kind == "TEXT" and existing.reference in valid_references:
                merged_records.append(existing)

        return merged_records, preserved_toc_headings

    def _replace_data_section(
        self,
        *,
        original_text: str,
        records: list[InitializationRecord],
    ) -> str:
        rendered_records = "\n".join(_render_record(record) for record in records)

        if DATA_MARKER in original_text:
            head, _ = original_text.split(DATA_MARKER, 1)
            return f"{head.rstrip()}\n\n{DATA_MARKER}\n{rendered_records}\n"

        return f"{original_text.rstrip()}\n\n{DATA_MARKER}\n{rendered_records}\n"

    def _create_numbered_backup(self, source: Path) -> Path:
        counter = 1

        while True:
            backup = source.with_name(f"{source.name}.bak.{counter}")

            if not backup.exists():
                shutil.copy2(source, backup)
                return backup

            counter += 1


def _render_record(record: InitializationRecord) -> str:
    return (
        f"{record.kind};"
        f"{record.hash_value};"
        f"{record.reference};"
        f"{record.content};"
        f"{record.type_marker}"
    )
