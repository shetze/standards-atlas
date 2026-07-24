from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument

hypothesis = pytest.importorskip("hypothesis")
given = hypothesis.given
st = hypothesis.strategies

pytestmark = pytest.mark.property

SAFE_KEY = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_. /:\\",
    ),
    min_size=1,
    max_size=40,
).filter(lambda value: bool(value.strip()))
TITLE = st.text(min_size=1, max_size=120).filter(lambda value: bool(value.strip()))


@given(key=SAFE_KEY, title=TITLE)
def test_filesystem_roundtrip_is_stable_for_valid_document_values(
    key: str,
    title: str,
) -> None:
    with TemporaryDirectory() as directory:
        workspace = Path(directory) / ".atlas"
        repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
        document = EngineeringDocument(
            key=DocumentKey(value=key),
            title=title,
            document_type=DocumentType.OTHER,
        )

        repository.save(document)

        assert repository.load(document.key) == document


@given(key=SAFE_KEY)
def test_persisted_document_filename_never_escapes_workspace(key: str) -> None:
    with TemporaryDirectory() as directory:
        workspace = Path(directory) / ".atlas"
        repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
        document = EngineeringDocument(
            key=DocumentKey(value=key),
            title="Property test",
            document_type=DocumentType.OTHER,
        )

        repository.save(document)

        persisted = tuple((workspace / "documents").iterdir())
        assert len(persisted) == 1
        assert persisted[0].parent == workspace / "documents"
