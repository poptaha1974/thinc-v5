import json
from pathlib import Path

from thinc_v5.domain.common import ResearchPreviewResult


def test_assessment_schema_matches_committed_contract() -> None:
    contract_path = Path("docs/contracts/assessment-v1.json")

    committed = json.loads(contract_path.read_text(encoding="utf-8"))
    generated = ResearchPreviewResult[dict].model_json_schema()  # type: ignore[type-arg]

    assert generated == committed
