# THINC v5 Foundation Model Card

## Status

Research Preview

This Foundation release is a reviewable research preview, not a validated
release.

No predictive, causal, or field-tested performance claim is permitted before temporal and external validation.

## Intended Use

Use this package to record synthetic or reviewed economics evidence, compute
delivered contribution profit, and expose gate results for human review in the
Egyptian market (`EG`). It supports assessment intake, retrieval, and human
approval recording only.

## Prohibited Use

- Do not use this release as a production trading, campaign-launch, pricing,
  publishing, or budget-execution system.
- Do not use it as a production authentication boundary or a substitute for
  legal, privacy, or compliance review.
- Do not describe any output as predictive, causal, validated, or scientifically
  proven.

## Egyptian-Market Scope

The provenance validator currently requires `market == "EG"`. Thresholds,
assumptions, and example outcomes are therefore scoped to Egyptian commerce
operations and must not be transferred to another geography without new
calibration and validation work.

## Missing-Data Behavior

Missing money fields remain missing. The economics engine returns
`missingness_status = NOT_COLLECTED`, leaves delivered profit unset, and states
which required fields were absent. Missing evidence is never coerced to zero.

## Uncertainty

Current uncertainty reporting is structural, not empirical. The economics engine
emits deterministic uncertainty only when all required fields are present, and
`not_computable` uncertainty when required fields are missing. Confidence
intervals, calibration curves, and externally validated error bounds are not yet
available.

## Human Approval

Human approval is an explicit gate. `SCALE` is blocked unless all seven gates
pass and approval references the exact assessment ID, approver ID, and
timestamp. Production authentication is not implemented.

## Validation Status

Validation is pending. This release has not completed time-aware holdout
validation, external validation, live PostgreSQL release verification, or
field-pilot validation. It is not yet a validated release.

## Subgroup Risks

Subgroup risk analysis is not complete. Before any real-world pilot, the team
must review performance and operational harm by merchant size, category, COD
mix, fulfillment pattern, and any legally sensitive grouping allowed by policy.

## Rollback

Rollback for this release means holding or killing deployment of the Research
Preview workflow, rejecting high-impact use, and reverting to manual review if
any gate, data lineage field, or pilot safeguard is missing or contradicted.

## Known Limitations

- Only the delivered contribution economics engine is implemented.
- The API has no production auth and is safe only for explicit test identity
  injection.
- Local startup can use synthetic data only; synthetic evidence cannot establish
  scientific or operational validity.
- Live PostgreSQL verification was not run locally for this governance packet.
- No temporal, external, subgroup, causal, or predictive validation is complete.
