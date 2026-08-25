from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event, Lock, Thread, current_thread
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import text

import thinc_v5.decision.service as service_module
from tests.integration.db.conftest import MigratedDatabase
from thinc_v5.api.app import create_app
from thinc_v5.db.session import set_tenant_context
from thinc_v5.decision.service import (
    AssessmentInput,
    EngineRegistration,
    EngineRegistry,
    InMemoryAssessmentRepository,
    ReservationStateError,
    SqlAlchemyAssessmentRepository,
    StoredEngineOutput,
)
from thinc_v5.domain.economics import EconomicsAssessment
from thinc_v5.engines.economics import EconomicsEngine

pytest_plugins = ("tests.integration.db.conftest",)


class ReservationObservingPostgresRepository(SqlAlchemyAssessmentRepository):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            reservation_lease=timedelta(milliseconds=300),
            heartbeat_interval_seconds=0.05,
        )
        self.follower_waiting = Event()

    def _on_pending_wait(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> None:
        del tenant_id, idempotency_key
        self.follower_waiting.set()


def injected_test_identity(
    x_tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    x_test_identity: Annotated[str, Header(alias="X-Test-Identity")],
) -> dict[str, object]:
    return {"tenant_id": x_tenant_id, "actor_id": x_test_identity}


def build_client() -> TestClient:
    return TestClient(
        create_app(
            repository=InMemoryAssessmentRepository(),
            identity_provider=injected_test_identity,
        )
    )


TENANT_A_HEADERS = {
    "X-Tenant-ID": "11111111-1111-4111-8111-111111111111",
    "X-Test-Identity": "researcher-1",
}
TENANT_B_HEADERS = {
    "X-Tenant-ID": "22222222-2222-4222-8222-222222222222",
    "X-Test-Identity": "researcher-2",
}


def complete_assessment_payload() -> dict[str, object]:
    return {
        "economics": {
            "collected_revenue": "1000",
            "product_cost": "300",
            "ad_spend": "200",
            "shipping": "80",
            "collection_fees": "20",
            "return_cost": "40",
            "variable_operations_cost": "60",
            "delivered_orders": 10,
        },
        "requested_decision": "RESEARCH",
        "compliance_passed": True,
        "liquidity_passed": True,
        "data_quality_passed": True,
        "sample_size_passed": True,
        "operational_recency_passed": True,
        "stop_loss_registered": False,
        "provenance": {
            "schema_version": "1.0.0",
            "model_version": "economics-engine.1",
            "engine_commit": "abc1234",
            "generated_at": "2026-08-25T08:00:00Z",
            "evidence_as_of": "2026-08-24T20:00:00Z",
            "market": "EG",
            "source_ids": ["source-1"],
        },
    }


def assert_key_absent(value: object, forbidden_key: str) -> None:
    if isinstance(value, dict):
        assert forbidden_key not in value
        for child in value.values():
            assert_key_absent(child, forbidden_key)
    elif isinstance(value, list):
        for child in value:
            assert_key_absent(child, forbidden_key)


def test_post_complete_assessment_returns_research_preview() -> None:
    response = build_client().post(
        "/v1/assessments",
        headers={
            **TENANT_A_HEADERS,
            "Idempotency-Key": "assessment-request-1",
        },
        json=complete_assessment_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "Research Preview"
    assert body["provenance"] == complete_assessment_payload()["provenance"]
    assert body["provenance"]["market"] == "EG"
    assert body["data"]["economics"]["delivered_contribution_profit"] == "300"
    assert len(body["data"]["gate_results"]) == 7
    assert body["decision_reasons"]
    assert_key_absent(body, "success_probability")


def test_post_idempotency_is_scoped_to_tenant_and_payload() -> None:
    client = build_client()
    headers_a = {**TENANT_A_HEADERS, "Idempotency-Key": "shared-key"}
    headers_b = {**TENANT_B_HEADERS, "Idempotency-Key": "shared-key"}

    first = client.post(
        "/v1/assessments",
        headers=headers_a,
        json=complete_assessment_payload(),
    )
    duplicate = client.post(
        "/v1/assessments",
        headers=headers_a,
        json=complete_assessment_payload(),
    )
    other_tenant = client.post(
        "/v1/assessments",
        headers=headers_b,
        json=complete_assessment_payload(),
    )
    changed_payload = complete_assessment_payload()
    assert isinstance(changed_payload["economics"], dict)
    changed_payload["economics"]["collected_revenue"] = "1001"
    conflict = client.post(
        "/v1/assessments",
        headers=headers_a,
        json=changed_payload,
    )

    assert first.status_code == duplicate.status_code == other_tenant.status_code == 201
    assert first.json() == duplicate.json()
    assert first.json()["assessment_id"] != other_tenant.json()["assessment_id"]
    assert conflict.status_code == 409
    assert conflict.headers["content-type"].startswith("application/problem+json")
    assert conflict.json()["status"] == 409


def test_get_is_tenant_isolated() -> None:
    client = build_client()
    created = client.post(
        "/v1/assessments",
        headers={**TENANT_A_HEADERS, "Idempotency-Key": "get-key"},
        json=complete_assessment_payload(),
    ).json()

    owner_response = client.get(
        f"/v1/assessments/{created['assessment_id']}",
        headers=TENANT_A_HEADERS,
    )
    other_response = client.get(
        f"/v1/assessments/{created['assessment_id']}",
        headers=TENANT_B_HEADERS,
    )

    assert owner_response.status_code == 200
    assert owner_response.json() == created
    assert other_response.status_code == 404


def test_validation_errors_use_rfc_9457_problem_details() -> None:
    invalid = complete_assessment_payload()
    assert isinstance(invalid["economics"], dict)
    invalid["economics"]["ad_spend"] = "-1"

    response = build_client().post(
        "/v1/assessments",
        headers={**TENANT_A_HEADERS, "Idempotency-Key": "invalid-key"},
        json=invalid,
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json().keys() >= {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "errors",
    }
    assert response.json()["status"] == 422


def test_postgresql_repository_persists_assessment_under_rls(
    migrated_database: MigratedDatabase,
) -> None:
    tenant_id = uuid4()
    with migrated_database.migration_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id}", "name": "Tenant"},
        )
    client = TestClient(
        create_app(
            repository=SqlAlchemyAssessmentRepository(migrated_database.app_engine),
            identity_provider=injected_test_identity,
        )
    )
    headers = {
        "X-Tenant-ID": str(tenant_id),
        "X-Test-Identity": "researcher-pg",
        "Idempotency-Key": "postgres-assessment-key",
    }

    created = client.post(
        "/v1/assessments",
        headers=headers,
        json=complete_assessment_payload(),
    )
    duplicate = client.post(
        "/v1/assessments",
        headers=headers,
        json=complete_assessment_payload(),
    )
    with migrated_database.app_engine.begin() as connection:
        set_tenant_context(connection, tenant_id)
        stored_outputs = connection.execute(
            text(
                "SELECT engine_name, output FROM engine_output_records "
                "WHERE assessment_id = :assessment_id"
            ),
            {"assessment_id": created.json()["assessment_id"]},
        ).all()

    assert created.status_code == 201
    assert duplicate.json() == created.json()
    assert len(stored_outputs) == 1
    assert stored_outputs[0].engine_name == "economics"
    assert stored_outputs[0].output["delivered_contribution_profit"] == "300"


def test_postgresql_concurrent_idempotency_has_one_executor_and_no_orphans(
    migrated_database: MigratedDatabase,
) -> None:
    tenant_id = uuid4()
    with migrated_database.migration_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id}", "name": "Tenant"},
        )
    repository = ReservationObservingPostgresRepository(migrated_database.app_engine)
    engine_started = Event()
    release_engine = Event()
    execution_lock = Lock()
    executions = 0
    economics_engine = EconomicsEngine()

    def blocking_economics(request: AssessmentInput):
        nonlocal executions
        with execution_lock:
            executions += 1
        engine_started.set()
        assert release_engine.wait(timeout=5)
        return economics_engine.assess(request.economics, request.provenance)

    client = TestClient(
        create_app(
            repository=repository,
            identity_provider=injected_test_identity,
            engine_registry=EngineRegistry(
                (
                    EngineRegistration(
                        name="economics",
                        run=blocking_economics,
                        output_model=EconomicsAssessment,
                    ),
                )
            ),
        )
    )
    headers = {
        "X-Tenant-ID": str(tenant_id),
        "X-Test-Identity": "researcher-pg",
        "Idempotency-Key": "postgres-concurrent-key",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            client.post,
            "/v1/assessments",
            headers=headers,
            json=complete_assessment_payload(),
        )
        assert engine_started.wait(timeout=5)
        second = executor.submit(
            client.post,
            "/v1/assessments",
            headers=headers,
            json=complete_assessment_payload(),
        )
        try:
            assert repository.follower_waiting.wait(timeout=5)
            time.sleep(0.7)
            assert executions == 1
            assert not second.done()
        finally:
            release_engine.set()
        responses = [first.result(timeout=5), second.result(timeout=5)]

    assert [response.status_code for response in responses] == [201, 201]
    assessment_id = responses[0].json()["assessment_id"]
    assert assessment_id == responses[1].json()["assessment_id"]
    assert executions == 1
    with migrated_database.app_engine.begin() as connection:
        set_tenant_context(connection, tenant_id)
        assessment_count = connection.execute(
            text(
                "SELECT count(*) FROM assessment_records WHERE idempotency_key = :key"
            ),
            {"key": "postgres-concurrent-key"},
        ).scalar_one()
        output_count = connection.execute(
            text(
                "SELECT count(*) FROM engine_output_records "
                "WHERE assessment_id = :assessment_id"
            ),
            {"assessment_id": assessment_id},
        ).scalar_one()
    assert assessment_count == 1
    assert output_count == 1


def test_postgresql_expired_owner_is_fenced_after_takeover(
    migrated_database: MigratedDatabase,
) -> None:
    tenant_id = uuid4()
    with migrated_database.migration_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id}", "name": "Tenant"},
        )
    repository = SqlAlchemyAssessmentRepository(
        migrated_database.app_engine,
        reservation_lease=timedelta(milliseconds=100),
        heartbeat_interval_seconds=0.02,
    )
    provenance: dict[str, object] = {"source_ids": ["source-1"]}
    stale = repository.reserve_assessment(
        tenant_id,
        "postgres-fencing-key",
        "sha256:request",
        provenance,
    )
    time.sleep(0.2)
    winner = repository.reserve_assessment(
        tenant_id,
        "postgres-fencing-key",
        "sha256:request",
        provenance,
    )
    winner_output = StoredEngineOutput(
        engine_name="economics",
        output={"value": "winner"},
        output_hash="sha256:winner",
        provenance=provenance,
    )
    repository.save_engine_output(
        tenant_id,
        winner.assessment_id,
        winner,
        winner_output,
    )

    assert winner.assessment_id == stale.assessment_id
    assert winner.fencing_epoch > stale.fencing_epoch
    with pytest.raises(ReservationStateError):
        repository.get_engine_output(
            tenant_id,
            stale.assessment_id,
            stale,
            "economics",
        )
    with pytest.raises(ReservationStateError):
        repository.save_engine_output(
            tenant_id,
            stale.assessment_id,
            stale,
            StoredEngineOutput(
                engine_name="economics",
                output={"value": "stale"},
                output_hash="sha256:stale",
                provenance=provenance,
            ),
        )
    with pytest.raises(ReservationStateError):
        repository.fail_assessment(
            tenant_id,
            "postgres-fencing-key",
            "sha256:request",
            stale,
        )
    assert (
        repository.get_engine_output(
            tenant_id,
            winner.assessment_id,
            winner,
            "economics",
        )
        == winner_output
    )


def test_postgresql_active_heartbeat_ignores_deliberately_skewed_callers(
    migrated_database: MigratedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_datetime = datetime

    class ThreadSkewedDateTime:
        @classmethod
        def now(cls, timezone: object = None) -> datetime:
            current = real_datetime.now(timezone)  # type: ignore[arg-type]
            if current_thread().name == "slow-caller-heartbeat":
                return current - timedelta(days=365)
            if current_thread().name.startswith("fast-caller-follower"):
                return current + timedelta(days=365)
            return current

        @classmethod
        def fromisoformat(cls, value: str) -> datetime:
            return real_datetime.fromisoformat(value)

    monkeypatch.setattr(service_module, "datetime", ThreadSkewedDateTime)
    tenant_id = uuid4()
    with migrated_database.migration_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id}", "name": "Tenant"},
        )
    repository = ReservationObservingPostgresRepository(migrated_database.app_engine)
    request_hash = "sha256:skewed-request"
    provenance: dict[str, object] = {"source_ids": ["source-1"]}
    owner = repository.reserve_assessment(
        tenant_id,
        "postgres-skewed-clock-key",
        request_hash,
        provenance,
    )
    stop_heartbeat = Event()
    heartbeat_renewed = Event()
    heartbeat_errors: list[BaseException] = []

    def heartbeat() -> None:
        while not stop_heartbeat.wait(0.04):
            try:
                repository.renew_assessment(
                    tenant_id,
                    "postgres-skewed-clock-key",
                    request_hash,
                    owner,
                )
                heartbeat_renewed.set()
            except BaseException as error:
                heartbeat_errors.append(error)
                return

    heartbeat_thread = Thread(
        target=heartbeat,
        name="slow-caller-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    assert heartbeat_renewed.wait(timeout=5)

    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="fast-caller-follower",
    ) as executor:
        follower = executor.submit(
            repository.reserve_assessment,
            tenant_id,
            "postgres-skewed-clock-key",
            request_hash,
            provenance,
        )
        try:
            assert repository.follower_waiting.wait(timeout=5)
            time.sleep(0.7)
            assert not follower.done()
            assert heartbeat_errors == []
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=5)
            if follower.done():
                live_owner = follower.result(timeout=5)
            else:
                live_owner = owner
            repository.fail_assessment(
                tenant_id,
                "postgres-skewed-clock-key",
                request_hash,
                live_owner,
            )
            if not follower.done():
                follower.result(timeout=5)
