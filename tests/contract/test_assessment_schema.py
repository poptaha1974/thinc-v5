import json
from pathlib import Path

from thinc_v5.domain.common import ResearchPreviewResult


def test_assessment_schema_matches_committed_contract() -> None:
    contract_path = Path("docs/contracts/assessment-v1.json")

    committed = json.loads(contract_path.read_text(encoding="utf-8"))
    generated = ResearchPreviewResult[dict].model_json_schema()  # type: ignore[type-arg]

    assert generated == committed
    assert "decision_reasons" in generated["properties"]
    assert "decision_reasons" in generated["required"]
    assert generated["properties"]["decision_reasons"] == {
        "items": {"minLength": 1, "pattern": ".*\\S.*", "type": "string"},
        "title": "Decision Reasons",
        "type": "array",
    }

    provenance = generated["$defs"]["Provenance"]
    source_ids = provenance["properties"]["source_ids"]

    assert source_ids["minItems"] == 1
    assert source_ids["items"] == {
        "minLength": 1,
        "pattern": ".*\\S.*",
        "type": "string",
    }

    uncertainty = generated["$defs"]["Uncertainty"]

    assert uncertainty["properties"]["method"] == {
        "minLength": 1,
        "pattern": ".*\\S.*",
        "title": "Method",
        "type": "string",
    }
    assert uncertainty["properties"]["notes"] == {
        "items": {"minLength": 1, "pattern": ".*\\S.*", "type": "string"},
        "title": "Notes",
        "type": "array",
    }
