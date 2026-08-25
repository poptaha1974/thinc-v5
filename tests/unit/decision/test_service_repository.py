from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID

from thinc_v5.decision.service import SqlAlchemyAssessmentRepository


class EmptyResult:
    def scalar_one_or_none(self) -> None:
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object | None]] = []

    def in_transaction(self) -> bool:
        return True

    def execute(
        self,
        statement: object,
        parameters: object | None = None,
    ) -> EmptyResult:
        self.calls.append((statement, parameters))
        return EmptyResult()


class RecordingEngine:
    def __init__(self) -> None:
        self.connection = RecordingConnection()

    @contextmanager
    def begin(self):
        yield self.connection


def test_sql_repository_sets_transaction_local_tenant_context_before_read() -> None:
    engine = RecordingEngine()
    repository = SqlAlchemyAssessmentRepository(engine)  # type: ignore[arg-type]
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")

    result = repository.get_assessment(tenant_id, "assessment-1")

    assert result is None
    assert len(engine.connection.calls) == 2
    context_statement, context_parameters = engine.connection.calls[0]
    select_statement, select_parameters = engine.connection.calls[1]
    assert "set_config('app.tenant_id'" in str(context_statement)
    assert context_parameters == {"tenant_id": str(tenant_id)}
    assert "assessment_records" in str(select_statement)
    assert select_parameters is None
