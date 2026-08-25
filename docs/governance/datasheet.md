# THINC v5 Foundation Datasheet

## Overview

This datasheet covers the Foundation release artifacts that support a
Research Preview assessment workflow. The current implementation stores
economics evidence, provenance metadata, gate outcomes, and human approvals.

## Persistence Reality and Atomicity

At the API boundary, `EconomicsInput` accepts only the documented economics
fields. The evidence `raw_payload` is the validated API representation, not the original HTTP bytes;
unknown request fields are not retained. The
`normalized_payload` is the canonical JSON-ready representation of the same
typed values. Foundation does not define fields for secrets or personal data,
and neither audit payload stores the economics body.

For PostgreSQL persistence, the evidence record, decision record, creation
audit event, and final assessment response are written in the
same PostgreSQL transaction that marks the assessment `COMPLETED`. If any governance write
fails, that transaction rolls back and the reservation is marked `FAILED` in a
separate recovery transaction. Engine outputs are intentionally durable before
completion so a fenced retry can reuse verified work; they are not themselves
evidence that an assessment completed.

Each evidence row stores raw and normalized SHA-256 hashes plus the full
source provenance block. Each decision row stores the
requested decision, safe recommended decision, and all seven gate reasons. A blocking gate changes the
safe recommendation to `HOLD`; it never executes that decision. Creation audit
events store the actor ID and the assessment, evidence, and decision entity
IDs. Approval and its audit event are also one atomic repository write.

Assessment and engine-output hashes are verified when records are loaded. A
mismatch fails closed rather than returning a response. The local devserver
uses an in-memory, process-lifetime repository; it is not PostgreSQL-backed and
is not durable.

## Delivered Profit Equation

Delivered contribution profit is currently computed as:

`collected_revenue - product_cost - ad_spend - shipping - collection_fees - return_cost - variable_operations_cost`

If `delivered_orders == 0`, the package still computes delivered contribution
profit but leaves `profit_per_delivered_order` unset.

## Decision Gates

The exact seven gates are:

1. `COMPLIANCE`
2. `LIQUIDITY`
3. `DELIVERED_PROFIT`
4. `DATA_QUALITY`
5. `SAMPLE_SIZE`
6. `OPERATIONAL_RECENCY`
7. `HUMAN_APPROVAL`

These gates are independent. A failing gate cannot be compensated for by any
aggregate score because no aggregate score exists in the API.

Approvals record human sign-off only. They do not recompute stored economics
outputs or stored gate results, and the API exposes no `SCALE` endpoint.

## Data Lineage Fields

Every research preview result is expected to carry the following lineage and
review fields:

- `schema_version`
- `model_version`
- `engine_commit`
- `generated_at`
- `evidence_as_of`
- `market`
- `data_quality_status`
- `missingness_status`
- `uncertainty`
- `source_ids`
- `review_status`
- `decision_reasons`

## Data Collection Boundaries

- The current release is scoped to `EG`.
- Real personal data is out of scope for local tests.
- Missing source fields remain explicit rather than imputed.
- Production authentication is not implemented, so real user collection is not
  authorized by this package alone.

## Outcomes For Future Validation

The next validation stages must predefine:

- Intermediate outcomes at 30 days: early operational recency, approval
  latency, evidence completeness, and stop-loss triggers.
- Primary delivered contribution outcomes at 60 days: delivered contribution
  profit and profit per delivered order.
- Intermediate outcomes at 90 days: persistence of delivered contribution,
  operational stability, and evidence quality.
- Primary delivered contribution outcomes at 180 days: delivered contribution
  profit, profit per delivered order, and cash recovery behavior.
- Follow-up outcomes at 365 days: persistence, retention, repeat purchase, and
  medium-term operational durability.

Secondary outcomes from the design spec remain:

- disciplined continuation and growth
- cash flow and capital payback period
- repeat purchase and retention
- direct demand, share of search, trust, and reviews
- learning completeness, evidence quality, and execution quality

## Scientific Methodology For Later Releases

Before any validated release claim, the team must execute:

- Group-aware and time-aware train, validation, and holdout splits.
- Baseline comparison against manual review and simpler rule baselines.
- Calibration analysis where probabilistic outputs exist, including Brier score.
- PR-AUC and ROC-AUC only when the target becomes a binary prediction task.
- Decision-curve analysis only when downstream decision thresholds are
  explicitly specified.
- Sensitivity analysis for weights, thresholds, and missing data handling.
- Independent temporal validation before external validation.

The Foundation release does not yet justify predictive or causal language.

## Follow-Up Phases

The planned follow-up sequence remains:

1. Egypt Commerce
2. Growth Experiments
3. Evidence and Research Pilot
4. Validation
5. Private SaaS
6. Scientific Release
