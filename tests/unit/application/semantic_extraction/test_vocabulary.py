from standards_atlas.application.semantic_extraction import FormalOntologyVocabulary
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE


def test_vocabulary_indexes_declared_classes_and_properties() -> None:
    vocabulary = FormalOntologyVocabulary.load(
        ("standards-atlas-core@1.1.0", "functional-safety@1.1.0")
    )
    assert f"{FORMAL_SEMANTIC_NAMESPACE}VerificationActivity" in vocabulary.classes
    assert f"{FORMAL_SEMANTIC_NAMESPACE}requires" in vocabulary.properties
    assert f"{FORMAL_SEMANTIC_NAMESPACE}confidence" in vocabulary.properties
