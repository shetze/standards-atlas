import json
from pathlib import Path

from standards_atlas.adapters.docling import DoclingJsonReader
from standards_atlas.application.model import ExtractedCode


def test_docling_code_is_mapped_to_extracted_code(tmp_path: Path) -> None:
    source = tmp_path / "document.json"
    source.write_text(
        json.dumps(
            {
                "name": "sample",
                "texts": [
                    {
                        "self_ref": "#/texts/0",
                        "label": "code",
                        "text": "x = 1",
                        "prov": [{"page_no": 1}],
                    }
                ],
                "body": {"children": [{"$ref": "#/texts/0"}]},
            }
        ),
        encoding="utf-8",
    )
    document = DoclingJsonReader().read(source)
    assert isinstance(document.items[0], ExtractedCode)
    assert document.items[0].code == "x = 1"
