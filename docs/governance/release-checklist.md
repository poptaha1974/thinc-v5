# THINC v5 Foundation Release Checklist

## Release Posture

- Release class: `Research Preview`
- Deployment posture: synthetic-only local startup
- Supported market: `EG`
- Production authentication: not implemented

## Documentation Gates

- Model card present with Research Preview status and prohibited-use language.
- Datasheet present with lineage fields, equation, seven gates, and future
  methodology notes.
- Pilot protocol present with preregistration, consent, withdrawal, stop-loss,
  deviations log, and legal/privacy review.
- README present with safe startup instructions and synthetic-only disclosure.

## Implementation Checks

- OpenAPI paths are limited to assessment create, retrieval, and approval.
- No endpoint executes ads, budgets, publishing, launch, or scale actions.
- Missing data remains explicit instead of being coerced to zero.
- Human approval is required for `SCALE`.

## Scientific Review Checklist

- Define baseline comparisons before claiming uplift.
- Use group-aware and time-aware splits before validation claims.
- Add calibration metrics, including Brier score, when probabilistic outputs
  exist.
- Use PR-AUC and ROC-AUC only when the task becomes a binary prediction task.
- Use decision-curve analysis only with predeclared decision thresholds.
- Avoid predictive or causal language until external and temporal validation are
  complete.

## Release Blockers

- Python 3.12 CI verification pending.
- Live PostgreSQL verification pending.
- Production authentication implementation pending.
- Temporal and external validation pending.
- Subgroup risk review pending.

## Follow-Up Phases

1. Egypt Commerce
2. Growth Experiments
3. Evidence and Research Pilot
4. Validation
5. Private SaaS
6. Scientific Release
