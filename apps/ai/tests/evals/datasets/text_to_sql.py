"""
Text-to-SQL Eval Dataset.

15 NL queries with gold SQL patterns for evaluating BI Agent SQL generation.
Each scenario includes:
- Input: Natural language query
- Gold SQL pattern: Expected SQL structure
- Expected columns: Required columns in result
- Difficulty: easy, medium, hard

Run with:
    cd apps/ai && uv run python tests/evals/run_evals.py
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class SQLEvalScenario:
    """Single text-to-SQL evaluation scenario."""
    id: str
    nl_query: str
    gold_sql_pattern: str  # Key SQL elements that must be present
    expected_columns: List[str]  # Required columns in result
    time_hint: str  # Expected time range
    difficulty: str  # easy, medium, hard
    query_category: str  # aggregation, trend, breakdown, comparison


# 15 evaluation scenarios
SQL_EVAL_SCENARIOS: List[SQLEvalScenario] = [
    # Scenario 1: Simple aggregation
    SQLEvalScenario(
        id="sql_001",
        nl_query="Show total revenue last 30 days",
        gold_sql_pattern="SELECT SUM(credit) FROM transactions WHERE txn_date >= NOW() - INTERVAL '30 days'",
        expected_columns=["sum"],
        time_hint="last 30 days",
        difficulty="easy",
        query_category="aggregation",
    ),
    # Scenario 2: Expense breakdown by category
    SQLEvalScenario(
        id="sql_002",
        nl_query="Show expenses by category for last month",
        gold_sql_pattern="SELECT category, SUM(debit) FROM transactions WHERE debit > 0 GROUP BY category",
        expected_columns=["category", "sum"],
        time_hint="last 30 days",
        difficulty="medium",
        query_category="breakdown",
    ),
    # Scenario 3: Revenue trend over time
    SQLEvalScenario(
        id="sql_003",
        nl_query="Show revenue trend for last 90 days",
        gold_sql_pattern="SELECT DATE_TRUNC('week', txn_date), SUM(credit) FROM transactions GROUP BY DATE_TRUNC",
        expected_columns=["date", "sum"],
        time_hint="last 90 days",
        difficulty="medium",
        query_category="trend",
    ),
    # Scenario 4: Top vendors by spend
    SQLEvalScenario(
        id="sql_004",
        nl_query="What are my top 5 vendors by spend",
        gold_sql_pattern="SELECT description OR vendor, SUM(debit) FROM transactions GROUP BY description ORDER BY SUM DESC LIMIT 5",
        expected_columns=["vendor", "sum"],
        time_hint="last 90 days",
        difficulty="medium",
        query_category="breakdown",
    ),
    # Scenario 5: Monthly burn rate
    SQLEvalScenario(
        id="sql_005",
        nl_query="What is my monthly burn rate",
        gold_sql_pattern="SELECT SUM(debit) FROM transactions WHERE debit > 0 AND txn_date >= NOW() - INTERVAL '30 days'",
        expected_columns=["sum"],
        time_hint="last 30 days",
        difficulty="easy",
        query_category="aggregation",
    ),
    # Scenario 6: Compare revenue vs expenses
    SQLEvalScenario(
        id="sql_006",
        nl_query="Compare revenue and expenses for last quarter",
        gold_sql_pattern="SELECT SUM(credit) as revenue, SUM(debit) as expenses FROM transactions WHERE txn_date >= NOW() - INTERVAL '90 days'",
        expected_columns=["revenue", "expenses"],
        time_hint="last 90 days",
        difficulty="medium",
        query_category="comparison",
    ),
    # Scenario 7: AWS spend over time
    SQLEvalScenario(
        id="sql_007",
        nl_query="Show AWS spend over the last 3 months",
        gold_sql_pattern="SELECT DATE_TRUNC('month', txn_date), SUM(debit) FROM transactions WHERE description ILIKE '%aws%' GROUP BY DATE_TRUNC",
        expected_columns=["date", "sum"],
        time_hint="last 90 days",
        difficulty="medium",
        query_category="trend",
    ),
    # Scenario 8: Runway calculation
    SQLEvalScenario(
        id="sql_008",
        nl_query="How many months of runway do I have",
        gold_sql_pattern="SELECT runway_months FROM finance_snapshots ORDER BY snapshot_date DESC LIMIT 1",
        expected_columns=["runway_months"],
        time_hint="current",
        difficulty="easy",
        query_category="aggregation",
    ),
    # Scenario 9: Transaction count by vendor
    SQLEvalScenario(
        id="sql_009",
        nl_query="How many transactions per vendor last month",
        gold_sql_pattern="SELECT description, COUNT(*) FROM transactions GROUP BY description HAVING COUNT > 0",
        expected_columns=["vendor", "count"],
        time_hint="last 30 days",
        difficulty="medium",
        query_category="breakdown",
    ),
    # Scenario 10: Average transaction size
    SQLEvalScenario(
        id="sql_010",
        nl_query="What is the average transaction size",
        gold_sql_pattern="SELECT AVG(debit) FROM transactions WHERE debit > 0",
        expected_columns=["avg"],
        time_hint="last 30 days",
        difficulty="easy",
        query_category="aggregation",
    ),
    # Scenario 11: Revenue growth rate
    SQLEvalScenario(
        id="sql_011",
        nl_query="What is my revenue growth rate month over month",
        gold_sql_pattern="SELECT DATE_TRUNC('month', txn_date), SUM(credit), LAG(SUM(credit)) OVER (ORDER BY DATE_TRUNC) FROM transactions GROUP BY DATE_TRUNC",
        expected_columns=["date", "revenue", "growth"],
        time_hint="last 90 days",
        difficulty="hard",
        query_category="trend",
    ),
    # Scenario 12: Category spending percentage
    SQLEvalScenario(
        id="sql_012",
        nl_query="What percentage of spending goes to each category",
        gold_sql_pattern="SELECT category, SUM(debit) * 100.0 / (SELECT SUM(debit) FROM transactions) as percentage FROM transactions GROUP BY category",
        expected_columns=["category", "percentage"],
        time_hint="last 30 days",
        difficulty="hard",
        query_category="breakdown",
    ),
    # Scenario 13: Largest transactions
    SQLEvalScenario(
        id="sql_013",
        nl_query="Show me the 10 largest transactions",
        gold_sql_pattern="SELECT * FROM transactions ORDER BY debit DESC LIMIT 10",
        expected_columns=["id", "description", "debit", "txn_date"],
        time_hint="all time",
        difficulty="easy",
        query_category="breakdown",
    ),
    # Scenario 14: Weekly revenue pattern
    SQLEvalScenario(
        id="sql_014",
        nl_query="Show revenue pattern by week of year",
        gold_sql_pattern="SELECT EXTRACT(WEEK FROM txn_date), SUM(credit) FROM transactions GROUP BY EXTRACT(WEEK) ORDER BY EXTRACT(WEEK)",
        expected_columns=["week", "revenue"],
        time_hint="last 365 days",
        difficulty="hard",
        query_category="trend",
    ),
    # Scenario 15: Vendor baseline comparison
    SQLEvalScenario(
        id="sql_015",
        nl_query="Compare actual spend vs baseline for top vendors",
        gold_sql_pattern="SELECT v.vendor_name, v.avg_90d as baseline, SUM(t.debit) as actual FROM vendor_baselines v JOIN transactions t ON v.vendor_name = t.description GROUP BY v.vendor_name",
        expected_columns=["vendor", "baseline", "actual"],
        time_hint="last 90 days",
        difficulty="hard",
        query_category="comparison",
    ),
]


def get_sql_eval_scenarios() -> List[SQLEvalScenario]:
    """Return all SQL evaluation scenarios."""
    return SQL_EVAL_SCENARIOS


def get_scenario_by_id(scenario_id: str) -> SQLEvalScenario | None:
    """Get a specific scenario by ID."""
    for scenario in SQL_EVAL_SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    return None


_COLUMN_ALIASES: Dict[str, List[str]] = {
    "sum": ["sum(", "count(", "avg("],
    "vendor": ["vendor", "description"],
    "date": ["date_trunc", "extract(", "txn_date", "snapshot_date", "month", "week"],
    "revenue": ["credit", "revenue"],
    "expenses": ["debit", "expenses"],
    "growth": ["lag(", "growth"],
    "percentage": ["100.0", "percentage", "%"],
    "category": ["category"],
    "avg": ["avg("],
    "count": ["count("],
    "runway_months": ["runway_months"],
    "baseline": ["baseline"],
    "actual": ["actual"],
    "week": ["week", "extract(week"],
    "id": ["id"],
    "debit": ["debit"],
    "description": ["description"],
    "txn_date": ["txn_date"],
}


def _has_time_predicate(gold: str) -> bool:
    lowered = gold.lower()
    if "now()" in lowered or "interval" in lowered:
        return True
    return bool(
        re.search(
            r"\b(?:txn_date|created_at|snapshot_date)\b\s*(?:>=|<=|>|<|between)",
            lowered,
        )
    )


def _expected_columns_ratio(generated: str, expected_columns: List[str]) -> float:
    if not expected_columns:
        return 1.0

    generated_lower = generated.lower()
    if re.search(r"\bselect\s+\*", generated_lower):
        return 1.0

    matched = 0
    for column in expected_columns:
        aliases = _COLUMN_ALIASES.get(column.lower(), [column.lower()])
        if any(alias in generated_lower for alias in aliases):
            matched += 1
    return matched / len(expected_columns)


def evaluate_sql_output(generated_sql: str, scenario: SQLEvalScenario) -> dict:
    """Evaluate generated SQL using only checks applicable to the gold SQL."""
    generated_lower = generated_sql.lower()
    gold = scenario.gold_sql_pattern
    gold_lower = gold.lower()

    checks: Dict[str, bool] = {
        "select": bool(re.search(r"\bselect\b", generated_lower)),
        "tenant_id": "tenant_id" in generated_lower,
    }

    applicable = ["select", "tenant_id"]
    if _has_time_predicate(gold):
        checks["time_filter"] = bool(re.search(r"\b(?:now\s*\(|interval\b)", generated_lower))
        applicable.append("time_filter")
    if re.search(r"\bgroup\s+by\b", gold_lower):
        checks["group_by"] = bool(re.search(r"\bgroup\s+by\b", generated_lower))
        applicable.append("group_by")
    if re.search(r"\border\s+by\b", gold_lower):
        checks["order_by"] = bool(re.search(r"\border\s+by\b", generated_lower))
        applicable.append("order_by")

    columns_ratio = _expected_columns_ratio(generated_sql, scenario.expected_columns)
    checks["expected_columns"] = columns_ratio == 1.0
    applicable.append("expected_columns")

    weight = 1.0 / len(applicable)
    score = sum(
        weight * (columns_ratio if check == "expected_columns" else float(checks[check]))
        for check in applicable
    )
    score = round(min(1.0, score), 2)

    failures = []
    if not checks["select"]:
        failures.append("Missing SELECT statement")
    if not checks["tenant_id"]:
        failures.append("Missing tenant_id filter (security issue)")
    if "time_filter" in checks and not checks["time_filter"]:
        failures.append(f"Missing time filter for {scenario.time_hint}")
    if "group_by" in checks and not checks["group_by"]:
        failures.append("Missing GROUP BY required by the gold SQL")
    if "order_by" in checks and not checks["order_by"]:
        failures.append("Missing ORDER BY required by the gold SQL")
    if not checks["expected_columns"]:
        failures.append("Missing one or more expected result columns")

    passed = score >= 0.7 and all(checks[check] for check in ("select", "tenant_id"))
    if passed:
        if failures:
            reasons = [f"Passed with score {score:.2f}; unmet: " + "; ".join(failures)]
        else:
            reasons = ["All checks passed"]
    else:
        reasons = failures + [f"Score {score:.2f} below pass threshold 0.70"]

    return {
        "passed": passed,
        "score": score,
        "reasons": reasons,
        "checks": checks,
    }
