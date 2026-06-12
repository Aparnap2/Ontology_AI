"""Predictive Guardian — forecasting engine.

Pure deterministic trend analysis and prediction.
Standard library only (math, statistics, itertools).

V4 scope: simple linear extrapolation, moving averages, and
threshold-breach prediction. Extensible to ARIMA/Prophet later.
"""
from __future__ import annotations

from src.llmops.tracer import traced

import math
import statistics
from typing import Any


# ═══════════════════════════════════════════════════════════════════════
# Core Trend Functions
# ═══════════════════════════════════════════════════════════════════════


def linear_trend(values: list[float]) -> tuple[float, float]:
    """Compute linear regression slope and intercept.

    Uses ordinary least squares: y = slope * x + intercept.

    Args:
        values: Series of y-values (e.g., monthly MRR, burn rates).
               Must have at least 2 data points.

    Returns:
        (slope, intercept) tuple.
        slope = change per period (positive = growing, negative = declining).

    Raises:
        ValueError: If fewer than 2 data points.
    """
    n = len(values)
    if n < 2:
        raise ValueError(
            f"Need at least 2 data points for linear trend, got {n}"
        )

    # X values are 0, 1, 2, ..., n-1
    x_sum = n * (n - 1) / 2  # Σx = n*(n-1)/2
    y_sum = sum(values)

    # Σxy = Σ(i * values[i]) for i = 0..n-1
    xy_sum = sum(i * v for i, v in enumerate(values))

    # Σx² = Σ(i²) for i = 0..n-1 = (n-1)*n*(2n-1)/6
    x2_sum = (n - 1) * n * (2 * n - 1) / 6

    # slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
    denominator = n * x2_sum - x_sum * x_sum
    if denominator == 0:
        return (0.0, y_sum / n if n > 0 else 0.0)

    slope = (n * xy_sum - x_sum * y_sum) / denominator
    intercept = (y_sum - slope * x_sum) / n

    return (slope, intercept)


def predict_next(values: list[float], periods_ahead: int = 1) -> float:
    """Predict next value using linear trend extrapolation.

    Fits a linear regression to `values`, then predicts the value
    `periods_ahead` periods into the future.

    Args:
        values: Historical data points (most recent last).
        periods_ahead: Number of periods to forecast ahead (default 1).

    Returns:
        Predicted value.

    Raises:
        ValueError: If fewer than 2 data points or periods_ahead < 1.
    """
    if periods_ahead < 1:
        raise ValueError(
            f"periods_ahead must be >= 1, got {periods_ahead}"
        )

    slope, intercept = linear_trend(values)
    # Last x value is len(values) - 1; predict at len(values) - 1 + periods_ahead
    next_x = len(values) - 1 + periods_ahead
    return slope * next_x + intercept


def predict_series(values: list[float], periods_ahead: int = 3) -> list[float]:
    """Predict multiple future values.

    Returns a list of `periods_ahead` predicted values, each one
    period further into the future.

    Args:
        values: Historical data points.
        periods_ahead: Number of future periods to predict.

    Returns:
        List of predicted values.

    Raises:
        ValueError: If periods_ahead < 1.
    """
    if periods_ahead < 1:
        raise ValueError(
            f"periods_ahead must be >= 1, got {periods_ahead}"
        )

    return [predict_next(values, periods_ahead=i) for i in range(1, periods_ahead + 1)]


def days_to_threshold(
    current_value: float,
    historical_values: list[float],
    threshold: float,
    above: bool = True,
) -> int | None:
    """Predict number of periods until a metric crosses a threshold.

    Uses linear trend to estimate when the value will cross `threshold`.

    Args:
        current_value: Most recent value.
        historical_values: Previous values for trend computation.
        threshold: The threshold value to check against.
        above: If True, check when value goes ABOVE threshold.
               If False, check when value goes BELOW threshold.

    Returns:
        Number of periods until crossing, or None if trend moves away
        from threshold (never crosses).
    """
    # Need at least 2 data points for a trend
    if len(historical_values) < 2:
        return None

    # Check if already past threshold
    if above and current_value >= threshold:
        return 0
    if not above and current_value <= threshold:
        return 0

    slope, intercept = linear_trend(historical_values)

    # Check if trend moves toward threshold
    if above and slope <= 0:
        return None  # Trend is flat or declining, never reaching above threshold
    if not above and slope >= 0:
        return None  # Trend is flat or rising, never reaching below threshold

    # Solve: threshold = slope * x + intercept
    # => x = (threshold - intercept) / slope
    crossing_x = (threshold - intercept) / slope
    last_x = len(historical_values) - 1

    days = crossing_x - last_x
    if days < 0:
        return 0  # Already crossed

    return max(1, round(days))


# ═══════════════════════════════════════════════════════════════════════
# Statistical Helpers
# ═══════════════════════════════════════════════════════════════════════


def moving_average(values: list[float], window: int = 3) -> list[float]:
    """Compute simple moving average over a sliding window.

    Args:
        values: Time series data.
        window: Window size for averaging (default 3).

    Returns:
        List of averaged values (length = len(values) - window + 1).
        Empty list if window > len(values).
    """
    if window > len(values):
        return []

    result: list[float] = []
    for i in range(len(values) - window + 1):
        avg = sum(values[i : i + window]) / window
        result.append(avg)
    return result


def compute_confidence_interval(
    values: list[float], confidence: float = 0.95
) -> tuple[float, float]:
    """Compute confidence interval for a set of values.

    Uses normal approximation: mean ± z * (std / sqrt(n)).

    Args:
        values: Data points.
        confidence: Confidence level (default 0.95 for 95% CI).

    Returns:
        (lower_bound, upper_bound) tuple.
        Returns (mean, mean) if only 1 value.
        Returns (0, 0) if empty list.
    """
    if not values:
        return (0.0, 0.0)

    n = len(values)
    mean = statistics.mean(values)

    if n == 1:
        return (mean, mean)

    # Z-scores for common confidence levels
    z_scores = {
        0.90: 1.645,
        0.95: 1.96,
        0.99: 2.576,
        0.80: 1.282,
        0.85: 1.440,
        0.999: 3.291,
    }
    z = z_scores.get(confidence, 1.96)

    try:
        std = statistics.stdev(values)
    except statistics.StatisticsError:
        std = 0.0

    margin = z * std / math.sqrt(n)

    return (mean - margin, mean + margin)


def compute_volatility(values: list[float]) -> float:
    """Compute coefficient of variation as a volatility measure.

    CV = std / mean. Higher values = more volatile.

    Args:
        values: Data points.

    Returns:
        Coefficient of variation (0 if mean is 0 or empty).
    """
    if not values or len(values) < 2:
        return 0.0

    mean = statistics.mean(values)
    if mean == 0:
        return 0.0

    try:
        std = statistics.stdev(values)
    except statistics.StatisticsError:
        return 0.0

    return std / mean


# ═══════════════════════════════════════════════════════════════════════
# High-Level Forecast Functions
# ═══════════════════════════════════════════════════════════════════════


def runway_depletion_date(
    current_burn_rate: float,
    current_runway_days: int,
    mrr_growth_trend: list[float] | None = None,
    burn_growth_trend: list[float] | None = None,
) -> dict[str, Any]:
    """Predict effective runway considering growth trends.

    If growth trends provided, adjusts the linear depletion projection
    to account for changing burn rate and revenue growth.

    Args:
        current_burn_rate: Current monthly burn in cents.
        current_runway_days: Current runway estimate in days.
        mrr_growth_trend: Historical MRR values for growth projection.
        burn_growth_trend: Historical burn values for burn trajectory.

    Returns:
        dict with:
        - base_runway_days: Current runway from signals.
        - adjusted_runway_days: Runway adjusted for predicted trends.
        - depletion_date: Estimated depletion date description.
        - confidence: Qualitative confidence ("high", "medium", "low").
    """
    base_runway_days = current_runway_days
    adjustment_factor = 1.0

    mrr_trend_label = "stable"
    burn_trend_label = "stable"

    # Adjust for MRR growth (revenue growth extends runway)
    if mrr_growth_trend is not None and len(mrr_growth_trend) >= 2:
        mrr_slope, _ = linear_trend(mrr_growth_trend)
        mean_mrr = statistics.mean(mrr_growth_trend)
        if mean_mrr > 0:
            mrr_growth_rate = mrr_slope / mean_mrr
            # Each 1% monthly growth extends runway by ~5% (heuristic)
            adjustment_factor += mrr_growth_rate * 5
            mrr_trend_label = (
                "improving" if mrr_growth_rate > 0.005 else
                "declining" if mrr_growth_rate < -0.005 else
                "stable"
            )

    # Adjust for burn acceleration (rising burn shortens runway)
    if burn_growth_trend is not None and len(burn_growth_trend) >= 2:
        burn_slope, _ = linear_trend(burn_growth_trend)
        mean_burn = statistics.mean(burn_growth_trend)
        if mean_burn > 0:
            burn_growth_rate = burn_slope / mean_burn
            # Each 1% monthly burn increase shortens runway by ~5%
            adjustment_factor -= burn_growth_rate * 5
            burn_trend_label = (
                "accelerating" if burn_growth_rate > 0.005 else
                "declining" if burn_growth_rate < -0.005 else
                "stable"
            )

    # Clamp adjustment factor to sensible range
    adjustment_factor = max(0.1, min(3.0, adjustment_factor))
    adjusted_runway_days = max(0, round(base_runway_days * adjustment_factor))

    # Determine confidence
    if adjustment_factor > 1.5 or adjustment_factor < 0.5:
        confidence = "low"
    elif adjustment_factor > 1.2 or adjustment_factor < 0.8:
        confidence = "medium"
    else:
        confidence = "high"

    # Build depletion description
    if adjusted_runway_days >= 365:
        depletion_desc = f"~{adjusted_runway_days // 30} months ({adjusted_runway_days} days)"
    elif adjusted_runway_days >= 30:
        depletion_desc = f"~{adjusted_runway_days // 30} month(s) ({adjusted_runway_days} days)"
    else:
        depletion_desc = f"{adjusted_runway_days} days"

    return {
        "base_runway_days": base_runway_days,
        "adjusted_runway_days": adjusted_runway_days,
        "depletion_date_description": depletion_desc,
        "confidence": confidence,
        "burn_trend": burn_trend_label,
        "mrr_trend": mrr_trend_label,
    }


def churn_acceleration_risk(
    churn_rates: list[float],
    acceleration_threshold: float = 1.5,
) -> dict[str, Any]:
    """Detect if churn is accelerating.

    Compares recent churn trend (last 3 periods) vs overall trend.
    If recent slope is `acceleration_threshold`x steeper → risk.

    Args:
        churn_rates: Monthly churn rates (most recent last).
        acceleration_threshold: Multiplier threshold (default 1.5x).

    Returns:
        dict with:
        - accelerating: bool
        - overall_slope: float
        - recent_slope: float
        - risk_level: str ("low", "medium", "high", "critical")
        - description: str
    """
    # Need at least 4 points for meaningful comparison
    if len(churn_rates) < 4:
        return {
            "accelerating": False,
            "overall_slope": 0.0,
            "recent_slope": 0.0,
            "risk_level": "low",
            "description": "Insufficient data for churn trend analysis.",
        }

    overall_slope, _ = linear_trend(churn_rates)
    recent_slope, _ = linear_trend(churn_rates[-3:])

    # If overall trend is flat or negative, no acceleration risk
    if overall_slope <= 0:
        return {
            "accelerating": False,
            "overall_slope": round(overall_slope, 10),
            "recent_slope": round(recent_slope, 10),
            "risk_level": "low",
            "description": "Churn is stable or declining.",
        }

    # Overall trend is positive — churn is a concern.
    # accelerating=True means "churn is trending upward" (not necessarily
    # accelerating faster). risk_level differentiates severity.
    abs_overall = abs(overall_slope)
    if abs_overall < 1e-10:
        ratio = 1.0
    else:
        ratio = recent_slope / overall_slope

    is_accelerating = ratio > acceleration_threshold and recent_slope > 0

    if is_accelerating:
        if ratio > 2.5:
            risk_level = "critical"
            desc = "Churn is critically accelerating — immediate attention required."
        elif ratio > 2.0:
            risk_level = "high"
            desc = "Churn is significantly accelerating."
        else:
            risk_level = "high"
            desc = "Churn is accelerating above normal trend."
    else:
        risk_level = "medium"
        desc = "Churn is rising but not accelerating faster than the overall trend."

    return {
        "accelerating": True,  # Any positive churn trend is flagged as concerning
        "overall_slope": round(overall_slope, 10),
        "recent_slope": round(recent_slope, 10),
        "risk_level": risk_level,
        "description": desc,
    }


@traced(agent="predictive", signature="compute_forecast_summary", as_type="span")
def compute_forecast_summary(
    values: list[float], label: str = "metric"
) -> dict[str, Any]:
    """Compute a complete forecast summary for a metric.

    Combines trend, next prediction, confidence interval, volatility,
    and moving average into a single summary dict.

    Args:
        values: Historical values.
        label: Human-readable metric name.

    Returns:
        dict with:
        - label: str
        - current: float (last value)
        - trend: str ("improving", "declining", "stable")
        - next_prediction: float (1 period ahead)
        - confidence_interval: [lower, upper]
        - volatility: float
        - moving_average: float (3-period MA of last value)
        - data_points: int (count of values used)
    """
    if not values:
        return {
            "label": label,
            "current": 0.0,
            "trend": "stable",
            "next_prediction": 0.0,
            "confidence_interval": [0.0, 0.0],
            "volatility": 0.0,
            "moving_average": 0.0,
            "data_points": 0,
        }

    current = values[-1]

    if len(values) < 2:
        return {
            "label": label,
            "current": current,
            "trend": "stable",
            "next_prediction": current,
            "confidence_interval": [current, current],
            "volatility": 0.0,
            "moving_average": current,
            "data_points": 1,
        }

    slope, _ = linear_trend(values)
    next_pred = predict_next(values)

    # Determine trend direction
    if abs(slope) < 0.001:
        trend = "stable"
    elif slope > 0:
        trend = "improving"
    else:
        trend = "declining"

    ci_lower, ci_upper = compute_confidence_interval(values)
    vol = compute_volatility(values)

    # Moving average of last window
    if len(values) >= 3:
        ma_vals = moving_average(values, window=3)
        ma_last = ma_vals[-1] if ma_vals else current
    else:
        ma_vals = moving_average(values, window=2)
        ma_last = ma_vals[-1] if ma_vals else current

    return {
        "label": label,
        "current": round(current, 10),
        "trend": trend,
        "next_prediction": round(next_pred, 10),
        "confidence_interval": [round(ci_lower, 10), round(ci_upper, 10)],
        "volatility": round(vol, 10),
        "moving_average": round(ma_last, 10),
        "data_points": len(values),
    }


__all__ = [
    "linear_trend",
    "predict_next",
    "predict_series",
    "days_to_threshold",
    "moving_average",
    "compute_confidence_interval",
    "compute_volatility",
    "runway_depletion_date",
    "churn_acceleration_risk",
    "compute_forecast_summary",
]
