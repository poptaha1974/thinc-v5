# THINC v5 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** بناء نواة Research Preview قابلة للتشغيل والاختبار، تتضمن عقود البيانات، محركات التقييم، بوابات القرار، التتبع، وواجهة API موحدة من دون أي تنفيذ آلي لقرارات تجارية عالية الأثر.

**Architecture:** تطبيق Python معياري يبدأ كـ modular monolith: نطاقات مستقلة داخل حزمة واحدة، PostgreSQL للتخزين، وFastAPI كواجهة. جميع المحركات نقية قدر الإمكان وتنتج عقودًا موحدة؛ طبقة القرار تجمع المخرجات وتطبق بوابات مانعة لا يمكن تعويضها بدرجة كلية.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL 16, pytest, Hypothesis, mypy, Ruff, Bandit, pip-audit, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-thinc-v5-platform-design.md`

## Global Constraints

- حالة المنتج تظل `Research Preview` حتى استيفاء التحقق الزمني والخارجي.
- لا توجد درجة كلية تسمح بتجاوز مانع قانوني أو خسارة اقتصادية.
- البيانات المفقودة تمثل بقيمة `NOT_COLLECTED` ولا تتحول إلى صفر.
- كل نتيجة تحمل `schema_version`, `model_version`, `engine_commit`, `generated_at`, `evidence_as_of`, `market`, `data_quality_status`, `missingness_status`, `uncertainty`, `source_ids`, `review_status`, و`decision_reasons`.
- لا ميزانية أو نشر أو توسع أو تغيير نموذج دون موافقة بشرية صريحة.
- لا أسرار داخل المستودع، ولا بيانات شخصية حقيقية في الاختبارات.
- السوق الافتراضي للإصدار الأول هو `EG`، من دون نقل معايرته إلى سوق آخر.
- جميع حسابات المال تستخدم `Decimal` ولا تستخدم `float`.

## خريطة الملفات

```text
pyproject.toml                         إعداد الحزمة والأدوات والإصدارات المثبتة
compose.yaml                           PostgreSQL محلي للاختبار والتطوير
.env.example                           أسماء الإعدادات فقط بلا أسرار
.github/workflows/ci.yml               فحوص النوع والجودة والأمان والاختبارات
src/thinc_v5/config.py                 قراءة الإعدادات والتحقق منها
src/thinc_v5/domain/common.py          أنواع النسب والجودة وعدم اليقين
src/thinc_v5/domain/economics.py       مدخلات ومخرجات اقتصاديات الطلب
src/thinc_v5/domain/decisions.py       قرارات وبوابات وموافقة بشرية
src/thinc_v5/domain/engines.py         عقد المحرك الموحد وسجل المحركات
src/thinc_v5/engines/economics.py      حساب ربح المساهمة المسلم
src/thinc_v5/decision/gates.py         تقييم البوابات المانعة
src/thinc_v5/decision/service.py       تنسيق المحركات وإصدار التوصية
src/thinc_v5/db/base.py                قاعدة SQLAlchemy والجلسات
src/thinc_v5/db/models.py              سجلات الأدلة والتقييم والقرار والتدقيق
src/thinc_v5/api/app.py                مصنع FastAPI
src/thinc_v5/api/routes/assessments.py نقطة تقييم Research Preview
alembic.ini                            إعداد الترحيلات
alembic/env.py                         ربط metadata بقاعدة البيانات
alembic/versions/0001_foundation.py    المخطط الأول
tests/unit/                             اختبارات النطاق والمحركات والبوابات
tests/integration/                      اختبارات API وقاعدة البيانات
tests/contract/                         ثبات JSON Schema
docs/contracts/assessment-v1.json      مخطط عقد التقييم المنشور
docs/governance/model-card.md           بطاقة Research Preview
docs/governance/datasheet.md            وصف البيانات وحدودها
```

---

### Task 1: Project skeleton and quality gate

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `compose.yaml`
- Create: `src/thinc_v5/__init__.py`
- Create: `src/thinc_v5/config.py`
- Create: `tests/unit/test_config.py`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: لا شيء.
- Produces: `Settings(database_url: str, environment: Literal["test", "development", "production"])` وبيئة CI موحدة.

- [ ] **Step 1: Write the failing configuration test**

```python
from thinc_v5.config import Settings

def test_settings_rejects_missing_database_url() -> None:
    try:
        Settings(database_url="", environment="test")
    except ValueError as exc:
        assert "database_url" in str(exc)
    else:
        raise AssertionError("empty database_url must be rejected")
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/unit/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'thinc_v5'`.

- [ ] **Step 3: Add the package configuration and minimal settings**

Use a `src` layout in `pyproject.toml`; pin runtime dependencies to compatible minor versions and configure Ruff, mypy strict mode, pytest, and coverage. Implement:

```python
from typing import Literal
from pydantic import BaseModel, field_validator

class Settings(BaseModel):
    database_url: str
    environment: Literal["test", "development", "production"] = "development"

    @field_validator("database_url")
    @classmethod
    def require_database_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("database_url must not be empty")
        return value
```

Set `.env.example` to `THINC_DATABASE_URL=postgresql+psycopg://thinc:change-me@localhost:5432/thinc` and `THINC_ENVIRONMENT=development`. Configure `compose.yaml` with PostgreSQL 16, a named volume, and a health check; do not commit a real password.

- [ ] **Step 4: Add the CI checks**

Configure CI to run, in order: `ruff check .`, `ruff format --check .`, `mypy src`, `pytest --cov=thinc_v5 --cov-fail-under=90`, `bandit -r src`, and `pip-audit` on Python 3.12.

- [ ] **Step 5: Verify the quality gate**

Run: `ruff check .; ruff format --check .; mypy src; pytest tests/unit/test_config.py -v`

Expected: all commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example compose.yaml src tests .github/workflows/ci.yml
git commit -m "build: establish THINC v5 foundation"
```

### Task 2: Provenance, missingness, and uncertainty contracts

**Files:**
- Create: `src/thinc_v5/domain/common.py`
- Create: `tests/unit/domain/test_common.py`
- Create: `tests/contract/test_assessment_schema.py`
- Create: `docs/contracts/assessment-v1.json`

**Interfaces:**
- Consumes: Python package from Task 1.
- Produces: `MissingnessStatus`, `DataQualityStatus`, `ReviewStatus`, `Uncertainty`, `Provenance`, and `ResearchPreviewResult[T]`.

- [ ] **Step 1: Write failing missingness and provenance tests**

```python
from datetime import UTC, datetime
from thinc_v5.domain.common import MissingnessStatus, Provenance

def test_not_collected_is_distinct_from_zero() -> None:
    assert MissingnessStatus.NOT_COLLECTED.value == "NOT_COLLECTED"
    assert MissingnessStatus.NOT_COLLECTED.value != "0"

def test_provenance_requires_source_ids() -> None:
    try:
        Provenance(
            schema_version="1.0.0", model_version="research-preview.1",
            engine_commit="abc1234", generated_at=datetime.now(UTC),
            evidence_as_of=datetime.now(UTC), market="EG", source_ids=[]
        )
    except ValueError as exc:
        assert "source_ids" in str(exc)
    else:
        raise AssertionError("source_ids must not be empty")
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `pytest tests/unit/domain/test_common.py -v`

Expected: FAIL because `thinc_v5.domain.common` does not exist.

- [ ] **Step 3: Implement the common contracts**

Define string enums with exact values: `NOT_COLLECTED`, `PARTIAL`, `COMPLETE`; `POOR`, `ACCEPTABLE`, `GOOD`; and `PENDING`, `APPROVED`, `REJECTED`. Define `Uncertainty(method: str, lower: Decimal | None, upper: Decimal | None, notes: list[str])`. Define `Provenance` with all mandatory fields and validators for nonempty `source_ids`, timezone-aware dates, `market == "EG"`, and semantic `schema_version`.

- [ ] **Step 4: Freeze the JSON contract**

Generate `ResearchPreviewResult[dict].model_json_schema()` into `docs/contracts/assessment-v1.json`. In the contract test, load the committed JSON and assert exact equality with the generated schema so breaking changes require an explicit schema version bump.

- [ ] **Step 5: Run focused and contract tests**

Run: `pytest tests/unit/domain/test_common.py tests/contract/test_assessment_schema.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/thinc_v5/domain/common.py tests docs/contracts/assessment-v1.json
git commit -m "feat: define provenance and uncertainty contracts"
```

### Task 3: Delivered contribution economics engine

**Files:**
- Create: `src/thinc_v5/domain/economics.py`
- Create: `src/thinc_v5/domain/engines.py`
- Create: `src/thinc_v5/engines/economics.py`
- Create: `tests/unit/engines/test_economics.py`
- Create: `tests/property/test_economics_properties.py`

**Interfaces:**
- Consumes: `Provenance`, `MissingnessStatus`, and `Uncertainty` from Task 2.
- Produces: `EconomicsInput`, `EconomicsAssessment`, `Engine[I, O].assess(input: I, provenance: Provenance) -> O`, and `EconomicsEngine.assess(...)`.

- [ ] **Step 1: Write the failing formula test**

```python
from decimal import Decimal
from thinc_v5.domain.economics import EconomicsInput
from thinc_v5.engines.economics import EconomicsEngine

def test_delivered_contribution_profit_uses_all_variable_costs(provenance) -> None:
    data = EconomicsInput(
        collected_revenue=Decimal("1000"), product_cost=Decimal("300"),
        ad_spend=Decimal("200"), shipping=Decimal("80"),
        collection_fees=Decimal("20"), return_cost=Decimal("40"),
        variable_operations_cost=Decimal("60"), delivered_orders=10,
    )
    result = EconomicsEngine().assess(data, provenance)
    assert result.delivered_contribution_profit == Decimal("300")
    assert result.profit_per_delivered_order == Decimal("30")
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/engines/test_economics.py -v`

Expected: FAIL because the economics modules do not exist.

- [ ] **Step 3: Implement the engine contract and economics calculation**

Use a generic `Protocol` for `Engine`. Reject negative costs, negative revenue, and `delivered_orders < 0`. If any money field is missing, return `missingness_status=NOT_COLLECTED`, no profit, and a reason naming each missing field. If delivered orders are zero, profit may be calculated but `profit_per_delivered_order` must be `None` with a division-by-zero reason.

- [ ] **Step 4: Add property-based invariants**

Use Hypothesis `decimals(min_value=0, max_value=1_000_000, places=2)` to prove: increasing one cost while holding other inputs fixed never increases contribution profit; profit equals revenue minus the exact seven cost terms; and serialization/deserialization preserves Decimal values.

- [ ] **Step 5: Run unit and property tests**

Run: `pytest tests/unit/engines/test_economics.py tests/property/test_economics_properties.py -v`

Expected: PASS with at least 100 generated examples per property.

- [ ] **Step 6: Commit**

```bash
git add src/thinc_v5/domain/economics.py src/thinc_v5/domain/engines.py src/thinc_v5/engines tests
git commit -m "feat: add delivered contribution economics engine"
```

### Task 4: Independent decision and safety gates

**Files:**
- Create: `src/thinc_v5/domain/decisions.py`
- Create: `src/thinc_v5/decision/gates.py`
- Create: `tests/unit/decision/test_gates.py`

**Interfaces:**
- Consumes: `EconomicsAssessment` and common contracts.
- Produces: `Decision`, `GateName`, `GateResult`, `GateContext`, and `evaluate_gates(context: GateContext) -> tuple[GateResult, ...]`.

- [ ] **Step 1: Write the failing non-compensation test**

```python
from thinc_v5.decision.gates import evaluate_gates
from thinc_v5.domain.decisions import Decision, GateContext

def test_scale_is_blocked_by_negative_delivered_profit(positive_assessments) -> None:
    context = GateContext(
        requested_decision=Decision.SCALE,
        compliance_passed=True, liquidity_passed=True,
        data_quality_passed=True, sample_size_passed=True,
        delivered_profit_positive=False,
    )
    results = evaluate_gates(context)
    assert any(r.name.value == "DELIVERED_PROFIT" and not r.passed for r in results)
    assert all(r.override_allowed is False for r in results if not r.passed)
```

- [ ] **Step 2: Run the test and verify failure**

Run: `pytest tests/unit/decision/test_gates.py -v`

Expected: FAIL because decision contracts are absent.

- [ ] **Step 3: Implement exact decisions and gates**

Define decisions `RESEARCH`, `TEST`, `FIX`, `HOLD`, `REPOSITION`, `SCALE`, `KILL`. Define independent gates `COMPLIANCE`, `LIQUIDITY`, `DELIVERED_PROFIT`, `DATA_QUALITY`, `SAMPLE_SIZE`, `OPERATIONAL_RECENCY`, and `HUMAN_APPROVAL`. For `SCALE`, every gate must pass and human approval must include approver ID, timestamp, and the exact assessment ID. A failed gate has `override_allowed=False`.

- [ ] **Step 4: Add a decision matrix test**

Parameterize all seven decisions. Assert that `RESEARCH` can proceed with incomplete evidence while clearly marked, `TEST` needs compliance and a registered stop-loss, and `SCALE` needs every gate. Assert that no numeric engine score appears in the gate API.

- [ ] **Step 5: Run the decision suite**

Run: `pytest tests/unit/decision/test_gates.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/thinc_v5/domain/decisions.py src/thinc_v5/decision/gates.py tests/unit/decision
git commit -m "feat: enforce independent decision safety gates"
```

### Task 5: Persistence, tenant isolation, and audit trail

**Files:**
- Create: `src/thinc_v5/db/base.py`
- Create: `src/thinc_v5/db/models.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_foundation.py`
- Create: `tests/integration/db/test_tenant_isolation.py`
- Create: `tests/integration/db/test_audit_immutability.py`

**Interfaces:**
- Consumes: domain IDs and provenance from Tasks 2–4.
- Produces: `Tenant`, `EvidenceRecord`, `AssessmentRecord`, `DecisionRecord`, `HumanApprovalRecord`, and append-only `AuditEvent` tables.

- [ ] **Step 1: Write the failing isolation test**

Create tenants A and B, insert one assessment for A, set the database session tenant context to B, query assessments, and assert an empty result. Then attempt a direct fetch by A's assessment ID and assert no row is returned.

- [ ] **Step 2: Run the database test and verify failure**

Run: `pytest tests/integration/db/test_tenant_isolation.py -v`

Expected: FAIL because database models and migration are absent.

- [ ] **Step 3: Implement the schema and PostgreSQL RLS**

Give every business table a non-null `tenant_id`. Add PostgreSQL Row Level Security policies using `current_setting('app.tenant_id', true)`. Store evidence raw payload and normalized payload separately as JSONB; store hashes for integrity. Make audit events append-only by denying UPDATE and DELETE to the application role and add a trigger that rejects both operations.

- [ ] **Step 4: Add migration and rollback verification**

Run `alembic upgrade head`, inspect all tables and RLS policies, run `alembic downgrade base`, then `alembic upgrade head` again. Assert schema equality after the second upgrade.

- [ ] **Step 5: Run isolation and immutability tests**

Run: `pytest tests/integration/db/test_tenant_isolation.py tests/integration/db/test_audit_immutability.py -v`

Expected: PASS; cross-tenant reads return nothing and audit mutation raises a database permission error.

- [ ] **Step 6: Commit**

```bash
git add src/thinc_v5/db alembic.ini alembic tests/integration/db
git commit -m "feat: add tenant-isolated persistence and audit log"
```

### Task 6: Unified Research Preview assessment API

**Files:**
- Create: `src/thinc_v5/decision/service.py`
- Create: `src/thinc_v5/api/app.py`
- Create: `src/thinc_v5/api/routes/assessments.py`
- Create: `tests/integration/api/test_assessments.py`
- Create: `tests/security/test_high_impact_actions.py`

**Interfaces:**
- Consumes: economics engine, gates, persistence, and provenance.
- Produces: `POST /v1/assessments`, `GET /v1/assessments/{assessment_id}`, and `POST /v1/assessments/{assessment_id}/approvals`; no endpoint executes ads, budgets, publishing, or scaling.

- [ ] **Step 1: Write the failing API behavior test**

POST a complete economics payload with `X-Tenant-ID` and a test identity. Assert HTTP 201, `status == "Research Preview"`, market `EG`, a complete provenance block, delivered profit, gate results, and that the response does not contain a success probability.

- [ ] **Step 2: Run the API test and verify failure**

Run: `pytest tests/integration/api/test_assessments.py -v`

Expected: FAIL because the app and routes do not exist.

- [ ] **Step 3: Implement orchestration and endpoints**

Create an assessment ID before execution, run registered engines, persist each output, evaluate gates, and return decision reasons in Arabic-friendly UTF-8 JSON. Return RFC 9457 problem details for validation errors. Require an idempotency key for POST and return the prior result for a duplicate key within the same tenant.

- [ ] **Step 4: Prove high-impact actions are absent**

Inspect OpenAPI paths and assert none contain `publish`, `budget`, `execute`, `scale`, `launch`, or `ads`. Assert approval records cannot change an assessment's stored engine outputs.

- [ ] **Step 5: Run API, security, and contract suites**

Run: `pytest tests/integration/api tests/security tests/contract -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/thinc_v5/decision/service.py src/thinc_v5/api tests/integration/api tests/security
git commit -m "feat: expose unified research preview assessment API"
```

### Task 7: Governance documentation and release verification

**Files:**
- Create: `docs/governance/model-card.md`
- Create: `docs/governance/datasheet.md`
- Create: `docs/governance/pilot-protocol.md`
- Create: `docs/governance/release-checklist.md`
- Create: `tests/docs/test_required_disclosures.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: implemented contracts, endpoints, limitations, and test results.
- Produces: reviewable Research Preview release packet and an executable completeness check.

- [ ] **Step 1: Write the failing disclosure test**

Assert the model card contains exact headings for status, intended use, prohibited use, Egyptian-market scope, missing-data behavior, uncertainty, human approval, validation status, subgroup risks, rollback, and known limitations. Assert it contains `Research Preview` and does not contain `Validated Release` as the current status.

- [ ] **Step 2: Run the docs test and verify failure**

Run: `pytest tests/docs/test_required_disclosures.py -v`

Expected: FAIL because governance documents do not exist.

- [ ] **Step 3: Write the release packet**

Document the delivered-profit equation, exact seven gates, data lineage fields, 30/60/90/180/365-day outcomes, group-aware and time-aware split policy, baseline comparison, calibration/Brier/PR-AUC/ROC-AUC applicability, decision-curve analysis, and prohibition on predictive or causal claims before validation. The pilot protocol must require preregistration, consent, withdrawal, stop-loss, deviations log, and legal/privacy review before student data collection.

- [ ] **Step 4: Update README with safe startup instructions**

Document environment creation, dependency installation, PostgreSQL startup, migrations, test command, API startup, and a warning that synthetic test data cannot establish scientific performance.

- [ ] **Step 5: Run full release verification**

Run: `ruff check .; ruff format --check .; mypy src; pytest --cov=thinc_v5 --cov-fail-under=90; bandit -r src; pip-audit`

Expected: every command exits 0. Manually verify the OpenAPI surface has no high-impact execution endpoint and `git grep -nE '(api[_-]?key|token|secret|password)\s*[:=]\s*[^$<]'` reports no committed credential.

- [ ] **Step 6: Commit**

```bash
git add docs tests/docs README.md
git commit -m "docs: publish THINC v5 research preview governance pack"
```

## خطط المراحل التالية

لا يبدأ أي منها قبل نجاح Foundation بالكامل:

1. `Egypt Commerce`: موصلات Shopify/Amazon.eg والشحن، COD/RTO، وتطبيع اقتصاديات الطلب.
2. `Growth Experiments`: سجل الفرضيات، Stop-Loss، Meta/TikTok/Pipiads ضمن الشروط الرسمية، والكرياتيف.
3. `Evidence & Research Pilot`: EvidenceProposal، مراجعتان للتغييرات عالية الأثر، وبروتوكول Pilot.
4. `Validation`: التقسيم الزمني والخارجي، المعايرة، المقارنات المرجعية، وتحليل التفاوت.
5. `Private SaaS`: الهوية والأدوار واللوحات وإدارة الموافقات وعزل المستأجرين الشامل.
6. `Scientific Release`: حزمة إعادة الإنتاج، الورقة، Model Card النهائي، وDatasheet.

كل مرحلة تحتاج خطة تنفيذ مستقلة بعد مراجعة مخرجات المرحلة السابقة حتى لا تثبت عقودًا مبكرًا قبل وجود دليل عملي.
