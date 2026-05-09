"""
AnomalyState — state object for the AnomalyAgent.

The AnomalyAgent is triggered when PulseAgent detects an anomaly.
It explains the anomaly in plain English and suggests one action.
"""
from __future__ import annotations
from typing import Optional, TypedDict


class AnomalyState(TypedDict, total=False):
    # ── Identity ──────────────────────────────────────────────────
    tenant_id:           str

    # ── Anomaly details (passed from PulseAgent) ──────────────────
    metric_name:         str            # e.g. "MRR", "runway", "burn"
    current_value:       float          # current metric value
    baseline_value:      float          # expected/baseline value
    deviation_pct:       float          # % deviation from baseline
    anomaly_description: str            # human-readable description

    # ── Rule-based detection inputs ───────────────────────────────
    runway_days:         int            # runway in days
    mrr_change_pct:      float          # MRR change %
    burn_rate_cents:     int            # current burn rate in cents
    prev_burn_cents:     int            # previous burn rate in cents
    churned_customers:   int            # churned customer count

    # ── Rule-based detection outputs ──────────────────────────────
    anomaly_detected:    bool           # whether anomaly was detected
    anomaly_type:        str            # type of anomaly (e.g. "runway_drop")
    anomaly_severity:    str            # "critical" or "warning"
    threshold_used:      float          # threshold that triggered
    should_alert:        bool           # whether to send alert

    # ── Historical context from Qdrant ────────────────────────────
    past_episodes:       list[str]      # similar past anomalies from memory
    historical_context:  str            # prose summary of past episodes

    # ── DSPy-generated outputs ────────────────────────────────────
    explanation:         str            # plain-English explanation
    check_first:         str            # one thing to investigate first
    action_item:         str            # concrete action for the founder

    # ── Slack delivery ────────────────────────────────────────────
    slack_blocks:        list[dict]     # Block Kit JSON
    slack_result:        dict           # {"ok": bool, "channel": str}

    # ── Metadata ──────────────────────────────────────────────────
    data_sources:        list[str]
    error:               str
    error_node:          str
