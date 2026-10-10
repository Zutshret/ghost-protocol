"""Lookup tables for the simulator: what each fault does to the numbers.

Everything the simulator "knows" about faults lives here, so you can tune the
demo by editing numbers in this file without touching the logic.
"""

from __future__ import annotations

from shared.types import FEATURE_BASELINES, Hypothesis, Level

# --------------------------------------------------------------------------
# Peak values: what each feature reads at full fault severity (severity = 1).
# Features not listed for a fault stay at their healthy baseline.
# --------------------------------------------------------------------------
FAULT_PEAKS: dict[Hypothesis, dict[str, float]] = {
    Hypothesis.DB_FAULT: {
        "replication_lag_s": 8.0,
        "slow_queries": 40.0,
        "lock_waits": 25.0,
        "payment_error_rate": 0.25,
        "queue_depth": 120.0,
        "latency_ms": 900.0,
        "edge_error_rate": 0.12,
    },
    Hypothesis.BAD_DEPLOY: {
        "canary_error_rate": 0.30,
        "payment_error_rate": 0.20,
        "edge_error_rate": 0.15,
        "latency_ms": 500.0,
        "queue_depth": 60.0,
        # minutes_since_deploy and config_changes are handled specially in sim.py
    },
    Hypothesis.ATTACK: {
        "traffic_anomaly": 0.9,
        "failed_logins": 400.0,
        "suspicious_sources": 60.0,
        "request_rate": 600.0,
        "upstream_timeouts": 30.0,
        "edge_error_rate": 0.18,
        "latency_ms": 600.0,
        "queue_depth": 80.0,
        "payment_error_rate": 0.08,
    },
    Hypothesis.DEPENDENCY_TIMEOUT: {
        "upstream_timeouts": 45.0,
        "latency_ms": 1000.0,
        "queue_depth": 90.0,
        "edge_error_rate": 0.08,
        "payment_error_rate": 0.07,
    },
}

# --------------------------------------------------------------------------
# Turning a number into a level (low / medium / high).
# For most features: value >= medium_at is "medium", value >= high_at is "high".
# For INVERTED features, small is the abnormal direction:
#   value <= medium_at is "medium", value <= high_at is "high".
# Pick thresholds once and keep them fixed.
# --------------------------------------------------------------------------
THRESHOLDS: dict[str, tuple[float, float]] = {
    # feature: (medium_at, high_at)
    "request_rate": (150.0, 300.0),
    "edge_error_rate": (0.03, 0.08),
    "upstream_timeouts": (8.0, 20.0),
    "payment_error_rate": (0.03, 0.10),
    "queue_depth": (30.0, 80.0),
    "latency_ms": (250.0, 600.0),
    "replication_lag_s": (2.0, 5.0),
    "slow_queries": (10.0, 25.0),
    "lock_waits": (8.0, 18.0),
    "traffic_anomaly": (0.3, 0.6),
    "failed_logins": (30.0, 150.0),
    "suspicious_sources": (8.0, 30.0),
    "minutes_since_deploy": (60.0, 15.0),  # inverted: a RECENT deploy is the signal
    "canary_error_rate": (0.03, 0.10),
    "config_changes": (1.0, 3.0),
}
INVERTED: set[str] = {"minutes_since_deploy"}

# Features that are counts (rounded to whole numbers) or rates (kept in 0..1).
COUNT_FEATURES: set[str] = {
    "request_rate",
    "upstream_timeouts",
    "queue_depth",
    "slow_queries",
    "lock_waits",
    "failed_logins",
    "suspicious_sources",
    "config_changes",
}
RATE_FEATURES: set[str] = {
    "edge_error_rate",
    "payment_error_rate",
    "canary_error_rate",
    "traffic_anomaly",
}


def level_of(feature: str, value: float) -> Level:
    """Convert a raw reading into low / medium / high."""
    medium_at, high_at = THRESHOLDS[feature]
    if feature in INVERTED:
        if value <= high_at:
            return Level.HIGH
        if value <= medium_at:
            return Level.MEDIUM
        return Level.LOW
    if value >= high_at:
        return Level.HIGH
    if value >= medium_at:
        return Level.MEDIUM
    return Level.LOW


def _feature_max(feature: str) -> float:
    if feature == "minutes_since_deploy":
        return 700.0
    candidates = [FEATURE_BASELINES[feature]]
    for peaks in FAULT_PEAKS.values():
        if feature in peaks:
            candidates.append(peaks[feature])
    return max(candidates)


# Largest believable value per feature; used for random "flaky" readings.
FEATURE_MAX: dict[str, float] = {f: _feature_max(f) for f in FEATURE_BASELINES}
