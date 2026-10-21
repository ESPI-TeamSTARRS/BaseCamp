from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyDistribution:
    """Repartition cumulee des durees : `cumulative_counts[i]` observations <= `bounds[i]` secondes."""

    bounds: tuple[float, ...]
    cumulative_counts: tuple[int, ...]
    count: int
    total_seconds: float
