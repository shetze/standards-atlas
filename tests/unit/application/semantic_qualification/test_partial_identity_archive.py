"""The cascade archive must accept the same labels as live execution and resume."""

import json
from dataclasses import replace

import pytest
import test_partial_cascade as cascade

from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
)


class RepositoryGateway(cascade.Gateway):
    def generate_structured(self, request):
        result = super().generate_structured(request)
        # Reproduce the adapter/server distinction rather than echoing request.model.
        model = request.model.removeprefix("hf.co/")
        if model.split(":", 1)[0].lower().endswith("-gguf"):
            model = model.split(":", 1)[0]
        return replace(result, model=model)


def alias_run(tmp_path):
    gateways = cascade.Gateways()
    gateways.gateways = {key: RepositoryGateway() for key in gateways.gateways}
    report, _ = cascade.run(tmp_path, gateways=gateways)
    return report, gateways


def test_alias_responses_reach_archive_adoption_and_resume_without_extra_votes(tmp_path):
    report, gateways = alias_run(tmp_path)
    assert report["stages"][0]["newly_completed"] == 1
    assert len(gateways.requests) == 4
    original, _, _ = cascade.verify(tmp_path / "run")
    resumed, _ = cascade.run(tmp_path, gateways=gateways)
    assert resumed["request_timing_current_invocation"]["request_count"] == 0
    assert len(gateways.requests) == 4
    restored, _, _ = cascade.verify(tmp_path / "run")
    assert original.fingerprint == restored.fingerprint
    archive = archive_partial_cascade(
        root=tmp_path / "run",
        archive_directory=tmp_path / "archives",
        resources=cascade.RESOURCES,
    )
    batch = load_qualification_knowledge(archive)
    assert batch.selected_clause_count == 1
    primary = next(
        a for a in batch.candidates[0].attributes if a.path.endswith(".primary_function")
    )
    assert primary.decision.valid_votes == 4


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "hf.co/other/model-GGUF:Q4_K_M"),
        ("prompt_version", "different-prompt"),
    ],
)
def test_archive_rechecks_identity_even_when_observation_checksum_was_updated(
    tmp_path,
    field,
    value,
):
    alias_run(tmp_path)
    path = next((tmp_path / "run/stages").glob("*/models/*/*/cases/*/response.json"))
    response = json.loads(path.read_bytes())
    response[field] = value
    path.write_text(json.dumps(response))
    observation_path = path.parent / "partial-observation.json"
    observation = json.loads(observation_path.read_bytes())
    observation["response_sha256"] = structure_fingerprint(response)
    observation_path.write_text(json.dumps(observation))
    with pytest.raises(ValueError, match="identity mismatch"):
        cascade.verify(tmp_path / "run")
