from standards_atlas.application.knowledge_proposal_extraction import FormalOntologyVocabulary
from standards_atlas.domain.model import FORMAL_SEMANTIC_NAMESPACE


def test_vocabulary_indexes_only_explicit_source_extractable_terms() -> None:
    vocabulary = FormalOntologyVocabulary.load(
        ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")
    )
    assert f"{FORMAL_SEMANTIC_NAMESPACE}EngineeringArtifact" in vocabulary.classes
    assert f"{FORMAL_SEMANTIC_NAMESPACE}VerificationPlan" in vocabulary.classes
    assert f"{FORMAL_SEMANTIC_NAMESPACE}VerificationActivity" in vocabulary.classes
    assert f"{FORMAL_SEMANTIC_NAMESPACE}requires" in vocabulary.properties
    assert f"{FORMAL_SEMANTIC_NAMESPACE}specifies" in vocabulary.properties
    assert f"{FORMAL_SEMANTIC_NAMESPACE}providesEvidenceFor" in vocabulary.properties

    assert f"{FORMAL_SEMANTIC_NAMESPACE}Clause" not in vocabulary.classes
    assert f"{FORMAL_SEMANTIC_NAMESPACE}containsClause" not in vocabulary.properties
    assert f"{FORMAL_SEMANTIC_NAMESPACE}confidence" not in vocabulary.properties
    assert f"{FORMAL_SEMANTIC_NAMESPACE}assertionSubject" not in vocabulary.properties
    assert f"{FORMAL_SEMANTIC_NAMESPACE}TechniqueRecommendation" not in vocabulary.classes
    assert f"{FORMAL_SEMANTIC_NAMESPACE}RecommendationLevel" not in vocabulary.classes
    assert f"{FORMAL_SEMANTIC_NAMESPACE}recommendsTechnique" not in vocabulary.properties
    assert f"{FORMAL_SEMANTIC_NAMESPACE}hasRecommendationLevel" not in vocabulary.properties
