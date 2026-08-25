from __future__ import annotations

from typing import cast

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from thinc_v5.db.models import (
    BUSINESS_TABLE_NAMES,
    AssessmentRecord,
    AuditEvent,
    DecisionRecord,
    EngineOutputRecord,
    EvidenceRecord,
    HumanApprovalRecord,
    metadata,
)


def test_every_business_table_requires_tenant_id() -> None:
    assert BUSINESS_TABLE_NAMES
    for table_name in BUSINESS_TABLE_NAMES:
        tenant_id = metadata.tables[table_name].c.tenant_id
        assert tenant_id.nullable is False
        assert tenant_id.foreign_keys


def test_evidence_keeps_raw_and_normalized_jsonb_with_integrity_hashes() -> None:
    table = EvidenceRecord.__table__

    assert isinstance(table.c.raw_payload.type, postgresql.JSONB)
    assert isinstance(table.c.normalized_payload.type, postgresql.JSONB)
    assert table.c.raw_payload_hash.nullable is False
    assert table.c.normalized_payload_hash.nullable is False


def test_assessment_maps_text_domain_id_uniquely_within_tenant() -> None:
    table = cast(Table, AssessmentRecord.__table__)
    domain_id = table.c.domain_assessment_id

    assert isinstance(domain_id.type, String)
    assert domain_id.nullable is False
    assert {column.name for column in _unique(table, "tenant_id", "id").columns} == {
        "tenant_id",
        "id",
    }
    assert {
        column.name
        for column in _unique(table, "tenant_id", "domain_assessment_id").columns
    } == {"tenant_id", "domain_assessment_id"}
    assert any(
        "btrim(domain_assessment_id) <> ''" in str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )
    check_constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert [constraint.name for constraint in check_constraints] == [
        "ck_assessment_records_domain_assessment_id_non_blank"
    ]


def test_assessment_references_include_tenant_in_foreign_key() -> None:
    for model in (DecisionRecord, HumanApprovalRecord):
        table = cast(Table, model.__table__)
        foreign_keys = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and constraint.referred_table is AssessmentRecord.__table__
        ]

        assert len(foreign_keys) == 1
        assert [column.name for column in foreign_keys[0].columns] == [
            "tenant_id",
            "assessment_id",
        ]


def test_api_post_idempotency_keys_are_unique_within_each_tenant() -> None:
    for model in (AssessmentRecord, HumanApprovalRecord):
        table = cast(Table, model.__table__)

        assert table.c.idempotency_key.nullable is True
        assert {
            column.name
            for column in _unique(table, "tenant_id", "idempotency_key").columns
        } == {"tenant_id", "idempotency_key"}


def test_engine_outputs_are_independent_tenant_owned_records() -> None:
    table = cast(Table, EngineOutputRecord.__table__)

    assert table.name in BUSINESS_TABLE_NAMES
    assert table.c.tenant_id.nullable is False
    assert table.c.assessment_id.nullable is False
    assert table.c.engine_name.nullable is False
    assert isinstance(table.c.output.type, postgresql.JSONB)
    assert {
        column.name
        for column in _unique(
            table,
            "tenant_id",
            "assessment_id",
            "engine_name",
        ).columns
    } == {"tenant_id", "assessment_id", "engine_name"}


def test_persistence_models_are_not_domain_models() -> None:
    from pydantic import BaseModel

    for model in (EvidenceRecord, AssessmentRecord, AuditEvent):
        assert not issubclass(model, BaseModel)


def test_audit_table_compiles_as_postgresql_jsonb() -> None:
    table = cast(Table, AuditEvent.__table__)
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    sql = str(CreateTable(table).compile(dialect=dialect))

    assert "payload JSONB NOT NULL" in sql
    assert "integrity_hash VARCHAR(128) NOT NULL" in sql


def _unique(table: Table, *column_names: str) -> UniqueConstraint:
    constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == list(column_names)
    ]
    assert len(constraints) == 1
    return constraints[0]
