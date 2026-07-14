"""
OntologyAI v1.0 Agents — Agent Packages.

Core agents:
  - pulse:        PulseAgent — health monitoring, anomaly detection
  - anomaly:      AnomalyAgent — deep anomaly investigation
  - investor:     InvestorAgent — investor updates, milestone tracking
  - qa:           QAAgent — quality assurance, test generation
  - cofounder:    CofounderAgent — orchestrates employee agents
  - guardian:     GuardianAgent — alert generation and management

Specialist agents:
  - finance:      FinanceGraph — @finance Q&A (burn rate, runway, revenue)
  - data:         DataGraph — @data Q&A (engagement, cohorts, churn, KPIs)
  - ops:          OpsGraph — @ops Q&A (hiring, vendors, compliance, SOPs)

Legacy: bi, comms, hiring
"""

from __future__ import annotations

# Core agents
import src.agents.pulse
import src.agents.anomaly
import src.agents.investor
import src.agents.qa
import src.agents.cofounder
# Specialist agents
import src.agents.finance
import src.agents.data
import src.agents.ops
