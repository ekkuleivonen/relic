"""Pure storage backend hotness ranking math."""

from dataclasses import dataclass

from infra.db.models import StorageBackend

_PROBE_OPS = ("put_ms", "head_ms", "get_ms", "delete_ms")
_UNREACHABLE_SCORE = 10**12


@dataclass(frozen=True)
class ProbeSample:
    put_ms: int | None
    head_ms: int | None
    get_ms: int | None
    delete_ms: int | None


@dataclass(frozen=True)
class StorageBackendHotnessScore:
    storage_backend: StorageBackend
    avg_latency_ms: float
    reachable: bool
    sample_count: int


def average_probe_latency(samples: list[ProbeSample]) -> float | None:
    if not samples:
        return None
    averaged: list[float] = []
    for op_index, _op_name in enumerate(_PROBE_OPS):
        values = [
            int(getattr(sample, _PROBE_OPS[op_index]))
            for sample in samples
            if getattr(sample, _PROBE_OPS[op_index]) is not None
        ]
        if values:
            averaged.append(sum(values) / len(values))
    if not averaged:
        return None
    return sum(averaged) / len(averaged)


def score_storage_backend_hotness(
    storage_backend: StorageBackend, samples: list[ProbeSample]
) -> StorageBackendHotnessScore:
    avg = average_probe_latency(samples)
    if avg is None:
        return StorageBackendHotnessScore(
            storage_backend=storage_backend,
            avg_latency_ms=float(_UNREACHABLE_SCORE),
            reachable=False,
            sample_count=len(samples),
        )
    return StorageBackendHotnessScore(
        storage_backend=storage_backend,
        avg_latency_ms=avg,
        reachable=True,
        sample_count=len(samples),
    )


def rank_hotness(
    scores: list[StorageBackendHotnessScore],
) -> list[StorageBackendHotnessScore]:
    return sorted(
        scores,
        key=lambda score: (
            0 if score.reachable else 1,
            score.avg_latency_ms,
            score.storage_backend.name,
        ),
    )
