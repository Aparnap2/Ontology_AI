"""
PulseState — the complete state object threaded through every
LangGraph node of the PulseAgent.

Design rules:
  - All fields Optional with sane defaults → graph is resumable
    at any node without crashing on missing upstream data.
  - cents (not dollars) for all monetary values → no float drift.
  - data_sources list → used by the summariser to cite its inputs.
  - error / error_node → non-fatal error path skips to Slack send.
"""
from __future__ import annotations
from typing import Optional, TypedDict


class PulseState(TypedDict, total=False):
    # ── Identity ──────────────────────────────────────────────────
    tenant_id:           str            # UUID of the tenant

    # ── Raw data fetched from integrations ───────────────────────
    mrr_cents:           int            # current MRR in paise/cents
    arr_cents:           int            # MRR × 12
    active_customers:    int
    new_customers:       int            # this calendar month
    churned_customers:   int            # this calendar month
    expansion_cents:     int            # upsell MRR delta
    contraction_cents:   int            # downgrade MRR delta

    balance_cents:       int            # bank balance
    burn_30d_cents:      int            # 30-day trailing burn

    active_users_30d:    int            # product DB

    # ── Computed metrics ─────────────────────────────────────────
    runway_months:       float          # balance / burn
    net_revenue_churn:   float          # (contraction+churn−expansion) / prev MRR
    quick_ratio:         float          # (new+expansion) / (churn+contraction)

    # ── Historical context from Qdrant (previous snapshots) ──────
    prev_mrr_cents:      int            # last snapshot MRR
    mrr_growth_pct:      float          # % change vs prev snapshot
    historical_context:  str            # prose summary from Qdrant memory
    prev_burn_cents:     int            # previous 30-day burn (injected upstream from
                                        # Qdrant retrieval; defaults to same as burn_30d_cents
                                        # if not set by the caller)

    # ── DSPy-generated outputs ───────────────────────────────────
    narrative:           str            # 3-sentence business pulse summary
    anomalies_detected:  list[str]      # list of anomaly descriptions (may be empty)
    action_item:         str            # ONE concrete action for the founder

    # ── Slack delivery ───────────────────────────────────────────
    slack_blocks:        list[dict]     # Block Kit JSON
    slack_result:        dict           # {"ok": bool, "channel": str}

    # ── Metadata ─────────────────────────────────────────────────
    data_sources:        list[str]      # e.g. ["stripe_mock", "bank_mock"]
    snapshot_id:         str            # UUID of written mrr_snapshot row
    error:               str            # non-fatal error message
    error_node:          str            # which node errored
