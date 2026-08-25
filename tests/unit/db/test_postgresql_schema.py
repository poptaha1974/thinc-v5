from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from thinc_v5.db.models import (
    BUSINESS_TABLE_NAMES,
    AssessmentRecord,
    AuditEvent,
    EvidenceRecord,
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


def test_persistence_models_are_not_domain_models() -> None:
    from pydantic import BaseModel

    for model in (EvidenceRecord, AssessmentRecord, AuditEvent):
        assert not issubclass(model, BaseModel)


def test_audit_table_compiles_as_postgresql_jsonb() -> None:
    sql = str(CreateTable(AuditEvent.__table__).compile(dialect=postgresql.dialect()))

    assert "payload JSONB NOT NULL" in sql
    assert "integrity_hash VARCHAR(128) NOT NULL" in sql
