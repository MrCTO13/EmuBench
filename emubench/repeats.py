"""Three fresh processes, the median-throughput pass and a predeclared spread gate."""
from statistics import median

COUNT = 3
MAX_SPREAD = 0.10


def summarize(elapsed, frames):
    if len(elapsed)!=COUNT or any(type(ns) is not int or ns<=0 for ns in elapsed):
        raise ValueError("Expected three independent positive durations")
    rates = [1e9*frames/ns for ns in elapsed]
    middle = median(rates)
    spread = (max(rates)-min(rates))/middle
    return {"elapsed_ns":elapsed, "selected":rates.index(middle),
            "relative_spread":spread, "accepted":spread<=MAX_SPREAD}
