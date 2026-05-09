"""
Finance Guardian Agent — ACE Employee for finance domain.

Per PRD Section 7: One of three employee agents managed by Co-founder Agent.
Finance Guardian watches for:
- FG-01: Silent Churn Death (monthly_churn_pct > 3%)
- FG-02: Burn Multiple Creep (net_burn / net_new_arr > 2.0)
- FG-03: Customer Concentration Risk (top_customer > 30% MRR)
- FG-04: Runway Compression Acceleration
- FG-05: Failed Payment Cluster
- FG-06: Payroll Revenue Ratio Breach

Each agent reads MissionState, writes domain fields, implements Generator→Reflector→Curator.
"""
from .graph import FinanceGuardianGraph

__all__ = ["FinanceGuardianGraph"]