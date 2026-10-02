import json
import stat

from standards_atlas.adapters.filesystem.context_source_package_repository import (
    FileSystemContextSourcePackageRepository,
)
from standards_atlas.application.context import (
    ContextSourcePackageBinding,
    build_context_source_package,
    build_structured_context_candidates,
    select_structured_context,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)


def _package():
    clause = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
        heading="Protected heading",
        content=(TextBlock(id="t", text="Protected source text."),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )
    inventory = build_structured_context_candidates(document, clause)
    selection = select_structured_context(inventory)
    return build_context_source_package(document, inventory, selection)


def test_private_repository_roundtrip_and_public_binding_do_not_leak_text(tmp_path) -> None:
    repository = FileSystemContextSourcePackageRepository(tmp_path)
    package = _package()

    binding = repository.save(package)
    loaded = repository.load(binding)

    assert loaded == package
    public = json.dumps(binding.model_dump(mode="json"), sort_keys=True)
    assert "Protected source text" not in public
    assert "Protected heading" not in public
    directory = tmp_path / "context-source-packages"
    stored = next(directory.glob("*.json"))
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600


def test_hash_without_private_package_bytes_is_not_reported_as_available(tmp_path) -> None:
    repository = FileSystemContextSourcePackageRepository(tmp_path)
    package = _package()
    binding = ContextSourcePackageBinding(
        package_sha256="sha256:" + ("0" * 64),
        document_key=package.document_key,
        document_revision=package.document_revision,
        target_clause_id=package.target_clause_id,
        target_reference=package.target_reference,
        selection_contract_id=package.selection.contract_id,
        selection_profile_id=package.selection.profile.profile_id,
        selection_completeness=package.selection.completeness.value,
        selection_gap_codes=tuple(gap.code for gap in package.selection.gaps),
        fingerprints=package.fingerprints,
    )

    assert repository.load(binding) is None


def test_proposal_and_private_source_package_roundtrip_keep_binding_resolvable(tmp_path) -> None:
    from standards_atlas.adapters.filesystem import FileSystemDocumentKnowledgeProposalRepository
    from standards_atlas.domain.model import (
        CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
        DocumentKnowledgeProposal,
        KnowledgeProposalProvenance,
    )

    packages = FileSystemContextSourcePackageRepository(tmp_path)
    package = _package()
    binding = packages.save(package)
    proposal = DocumentKnowledgeProposal(
        proposal_run_id="run-evidence-roundtrip",
        source_document_key=package.document_key,
        context_source_bindings=(binding,),
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="synthetic-test",
            extractor_version="1",
            source_binding_contract_id=CONTEXT_SOURCE_PACKAGE_BINDING_CONTRACT,
        ),
    )
    proposals = FileSystemDocumentKnowledgeProposalRepository(tmp_path)
    proposals.save(proposal)

    reloaded = proposals.load(proposal.proposal_run_id, proposal.source_document_key)
    assert reloaded is not None
    assert reloaded.context_source_bindings == (binding,)
    assert packages.load(reloaded.context_source_bindings[0]) == package

    proposal_path = (
        tmp_path
        / "knowledge-proposals"
        / proposal.proposal_run_id
        / f"{proposal.source_document_key}.json"
    )
    public_proposal = proposal_path.read_text(encoding="utf-8")
    assert "Protected source text" not in public_proposal
    assert "Protected heading" not in public_proposal
