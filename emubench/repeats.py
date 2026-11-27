"""Three fresh processes, the median-throughput pass and a predeclared acceptance gate.

A pass only counts when its timed window is at least MIN_WINDOW_MS long, the three
passes agree within MAX_SPREAD and no pass ran hot or throttled. Rejected series are
kept locally with the reason, never ranked.
"""
import os
from statistics import median
import time

COUNT = 3
MAX_SPREAD = 0.03
MIN_WINDOW_MS = 10000
COOL_DOWN_S = 5
HOT = ("serious", "critical")


# Test-only overrides, read at call time. A public score records the values it used,
# and the score service only accepts the published defaults above.
def max_spread():
    return float(os.environ.get("EMUBENCH_MAX_SPREAD_OVERRIDE", MAX_SPREAD))


def min_window_ms():
    return int(os.environ.get("EMUBENCH_MIN_WINDOW_MS_OVERRIDE", MIN_WINDOW_MS))


def cool_down():
    """Idle between passes so each process starts from a similar thermal state."""
    seconds = float(os.environ.get("EMUBENCH_COOL_DOWN_S", COOL_DOWN_S))
    if seconds > 0:
        time.sleep(seconds)


def thermal_problem(windows):
    for window in windows or ():
        for side in ("before", "after"):
            state = (window or {}).get(side) or {}
            if state.get("thermal_state") in HOT:
                return "hot"
            if state.get("throttled") is True:
                return "throttled"
    return None


def summarize(elapsed, frames, conditions=None):
    if len(elapsed) != COUNT or any(type(ns) is not int or ns <= 0 for ns in elapsed):
        raise ValueError("Expected three independent positive durations")
    counts = list(frames) if isinstance(frames, (list, tuple)) else [frames] * COUNT
    if len(counts) != COUNT or any(type(n) is not int or n <= 0 for n in counts):
        raise ValueError("Expected three positive frame counts")
    rates = [1e9 * n / ns for n, ns in zip(counts, elapsed)]
    middle = median(rates)
    spread = (max(rates) - min(rates)) / middle
    reasons = []
    limit, window = max_spread(), min_window_ms()
    if spread > limit:
        reasons.append("spread")
    if min(elapsed) < window * 1_000_000:
        reasons.append("short-window")
    problem = thermal_problem(conditions)
    if problem:
        reasons.append(problem)
    return {"elapsed_ns": elapsed, "frames": counts, "selected": rates.index(middle),
            "relative_spread": spread, "max_spread": limit,
            "min_window_ns": window * 1_000_000,
            "accepted": not reasons, "rejected_for": reasons}
