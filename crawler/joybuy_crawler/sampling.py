"""Deterministic stratified review sampling (WP-17).

Strategy (docs/05 §10):
- keep the source star distribution via per-rating quotas (largest remainder);
- prefer reviews with media, then the most recent ones, inside each stratum;
- fully deterministic for a given ``(candidates, target, seed)`` — the job's
  persisted ``random_seed`` makes reruns reproducible;
- never fabricates proportions: quotas derive from actual source counts.

The output carries full sampling metadata so selections stay auditable.
"""

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SampleCandidate:
    """One source review offered to the sampler."""

    source_id: str
    rating: int
    reviewed_at: object = None  # timezone-aware datetime, or None if the source hides it
    has_media: bool = False
    position: int = 0


@dataclass
class SampleOutcome:
    selected: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


RATINGS = (1, 2, 3, 4, 5)


def _largest_remainder_quotas(sizes: dict[int, int], target: int) -> dict[int, int]:
    total = sum(sizes.values())
    quotas = {}
    remainders = []
    allocated = 0
    for rating in sorted(sizes):
        exact = target * sizes[rating] / total
        quotas[rating] = int(exact)
        allocated += quotas[rating]
        remainders.append((exact - quotas[rating], rating))
    # Hand the leftover seats to the largest fractional parts; ties go to the
    # smaller rating so the outcome stays deterministic.
    for _, rating in sorted(remainders, key=lambda item: (-item[0], item[1]))[: target - allocated]:
        quotas[rating] += 1
    return quotas


def _tiebreak(seed, source_id: str) -> str:
    return hashlib.sha256(f"{seed}:{source_id}".encode()).hexdigest()


def stratified_sample(candidates, *, target: int, seed, generated_at=None) -> SampleOutcome:
    if target < 1:
        raise ValueError("target must be at least 1.")
    ordered_candidates = sorted(candidates, key=lambda item: (item.position, item.source_id))
    total = len(ordered_candidates)
    metadata = {
        "target": target,
        "available": total,
        "seed": seed,
        "generated_at": generated_at.isoformat() if generated_at else None,
        "strategy": "stratified-rating/media/recency",
        "strata": {},
        "media_selected": 0,
    }
    if total == 0:
        return SampleOutcome(selected=[], metadata=metadata)

    if target >= total:
        selected = list(ordered_candidates)
    else:
        by_rating = {rating: [] for rating in RATINGS}
        for item in ordered_candidates:
            by_rating.setdefault(item.rating, []).append(item)
        sizes = {rating: len(items) for rating, items in by_rating.items() if items}
        quotas = _largest_remainder_quotas(sizes, target)
        selected = []
        for rating, quota in quotas.items():
            stratum = sorted(
                by_rating[rating],
                key=lambda item: (
                    not item.has_media,
                    0 if item.reviewed_at is not None else 1,
                    -(item.reviewed_at.timestamp() if item.reviewed_at is not None else 0),
                    _tiebreak(seed, item.source_id),
                ),
            )
            chosen = stratum[:quota]
            selected.extend(chosen)
            metadata["strata"][str(rating)] = {
                "available": len(by_rating[rating]),
                "selected": len(chosen),
            }
        metadata["media_selected"] = sum(1 for item in selected if item.has_media)

    # Report the source-order selection; keep strata metadata when sampled.
    final = sorted(selected, key=lambda item: (item.position, item.source_id))
    if target >= total:
        for rating in RATINGS:
            count = sum(1 for item in final if item.rating == rating)
            if count:
                metadata["strata"][str(rating)] = {
                    "available": count,
                    "selected": count,
                }
        metadata["media_selected"] = sum(1 for item in final if item.has_media)
        metadata["strategy"] = "all-available"
    return SampleOutcome(selected=[item.source_id for item in final], metadata=metadata)
