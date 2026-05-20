import time


def timer_start() -> float:
    return time.perf_counter()


def elapsed_ms(started_at: float, *, minimum: int = 1) -> int:
    return max(minimum, round((time.perf_counter() - started_at) * 1000))


def latency_metadata(
    started_at: float,
    *,
    db_latency_ms: int | None = None,
    remote_latency_ms: int | None = None,
) -> dict[str, int]:
    metadata = {"duration_ms": elapsed_ms(started_at)}
    if db_latency_ms is not None:
        metadata["db_latency_ms"] = db_latency_ms
    if remote_latency_ms is not None:
        metadata["remote_latency_ms"] = remote_latency_ms
    return metadata
