# THINC v5 Foundation Pilot Protocol

## Purpose

This protocol defines the minimum safeguards required before any pilot uses
student or merchant data. Foundation is still a Research Preview and cannot be
described as validated, predictive, or causal.

## Preregistration

Register the pilot question, target population, hypotheses, outcome windows
(30/60/90/180/365 days), gate thresholds, rollback conditions, and analysis plan
before collecting pilot data.

## Consent

Collect documented consent that explains the Research Preview status, intended
use, data fields collected, approval workflow, and the absence of validated
production claims.

## Withdrawal

Participants must have a documented withdrawal path. Withdrawal requests should
stop new data collection, mark the request in the audit trail, and route the
case for legal and privacy handling.

## Stop-Loss

Every `TEST` or pilot run must define a stop-loss threshold, an owner, a review
cadence, and an immediate halt path if economics, safety, or compliance
conditions deteriorate.

## Deviations Log

Any protocol deviation, schema drift, gate override request, or data-quality
issue must be recorded with timestamp, owner, rationale, and corrective action.

## Legal and Privacy Review

No student data collection starts before legal and privacy review.

The review must confirm lawful basis, retention, access controls, audit
obligations, and whether any subgroup analysis creates additional consent or
ethics requirements.

## Pilot Consent Packet

The consent packet must include:

- Research Preview status and known limitations.
- The exact seven gates and the role of human approval.
- A statement that production authentication is not implemented in Foundation.
- A statement that the pilot does not create a validated, causal, or predictive
  claim by itself.
