import pytest
from pydantic import ValidationError

from standards_atlas.adapters.docling.options import (
    DoclingAcceleratorDevice,
    DoclingConversionOptions,
)


def test_default_options_are_stable_and_json_compatible() -> None:
    options = DoclingConversionOptions()

    assert options.as_metadata() == {
        "enable_ocr": False,
        "extract_tables": True,
        "extract_pictures": True,
        "generate_page_images": False,
        "accelerator_device": "auto",
        "accelerator_threads": 4,
    }


def test_options_accept_all_supported_accelerators() -> None:
    for device in DoclingAcceleratorDevice:
        options = DoclingConversionOptions(accelerator_device=device)
        assert options.as_metadata()["accelerator_device"] == device.value


def test_options_are_immutable() -> None:
    options = DoclingConversionOptions()

    with pytest.raises(ValidationError):
        options.enable_ocr = True


def test_options_reject_non_positive_thread_count() -> None:
    with pytest.raises(ValidationError):
        DoclingConversionOptions(accelerator_threads=0)
