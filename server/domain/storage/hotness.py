"""Pure bucket hotness ranking math."""

from dataclasses import dataclass

from infra.db.models import Bucket

_PROBE_OPS = ("put_ms", "head_ms", "get_ms", "delete_ms")
_UNREACHABLE_SCORE = 10**12


@dataclass(frozen=True)
class ProbeSample:
    put_ms: int | None
    head_ms: int | None
    get_ms: int | None
    delete_ms: int | None


@dataclass(frozen=True)
class BucketHotnessScore:
    bucket: Bucket
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


def score_bucket_hotness(bucket: Bucket, samples: list[ProbeSample]) -> BucketHotnessScore:
    avg = average_probe_latency(samples)
    if avg is None:
        return BucketHotnessScore(
            bucket=bucket,
            avg_latency_ms=float(_UNREACHABLE_SCORE),
            reachable=False,
            sample_count=len(samples),
        )
    return BucketHotnessScore(
        bucket=bucket,
        avg_latency_ms=avg,
        reachable=True,
        sample_count=len(samples),
    )


def rank_hotness(scores: list[BucketHotnessScore]) -> list[BucketHotnessScore]:
    return sorted(
        scores,
        key=lambda score: (
            0 if score.reachable else 1,
            score.avg_latency_ms,
            score.bucket.name,
        ),
    )
