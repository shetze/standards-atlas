"""Reproducible configuration for the Docling PDF pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DoclingAcceleratorDevice(StrEnum):
    """Hardware device used by Docling model inference."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"
    XPU = "xpu"


class DoclingConversionOptions(BaseModel):
    """Stable subset of Docling options used by Standards Atlas."""

    model_config = ConfigDict(frozen=True)

    enable_ocr: bool = False
    extract_tables: bool = True
    extract_pictures: bool = True
    generate_page_images: bool = False
    accelerator_device: DoclingAcceleratorDevice = DoclingAcceleratorDevice.AUTO
    accelerator_threads: int = Field(default=4, ge=1)

    def as_metadata(self) -> dict[str, bool | int | str]:
        """Return a JSON-compatible representation for conversion metadata."""
        return self.model_dump(mode="json")
