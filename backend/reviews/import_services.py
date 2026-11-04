"""Review sampling ingestion and import (WP-17).

Crawler side: ``ingest_review_candidates`` turns one parsed review payload
into :class:`~joybuy_crawler.sampling.SampleCandidate` rows.
Import side: ``import_sampled_reviews`` (backend) takes the sampled source
reviews of one product, dedups reviewers through the WP-12 fingerprint
service, and upserts reviews idempotently with version history.
"""

import sys
from pathlib import Path

from django.utils import timezone

CRAWLER_DIR = Path(__file__).resolve().parents[2] / "crawler"
if str(CRAWLER_DIR) not in sys.path and CRAWLER_DIR.exists():
    sys.path.insert(0, str(CRAWLER_DIR))

from joybuy_crawler.sampling import SampleCandidate  # noqa: E402

from reviews.domain import (  # noqa: E402
    ReviewContentInvalid,
    ReviewSourceIdentityInvalid,
)
from reviews.models import Review  # noqa: E402
from reviews.services import (  # noqa: E402
    get_or_create_reviewer_from_source,
    mark_source_review_deleted,
    upsert_source_review,
)

# Reviews whose fields are this long are rejected by the domain; truncate
# import-side summaries instead of failing the whole batch.
_MAX_TITLE = 300
_MAX_BODY = 20000
_MAX_VARIANT = 300


def ingest_review_candidates(parsed_reviews, *, position_offset: int = 0):
    """Build sampler candidates from parsed review payloads.

    ``parsed_reviews`` items need ``source_id``, ``rating`` and optionally
    ``reviewed_at``, ``image_urls``/``video_urls`` and ``position``.
    """

    candidates = []
    for offset, payload in enumerate(parsed_reviews or []):
        source_id = str((payload or {}).get("source_id") or "").strip()
        rating = payload.get("rating")
        if not source_id or rating is None:
            continue
        has_media = bool(payload.get("image_urls") or payload.get("video_urls"))
        candidates.append(
            SampleCandidate(
                source_id=source_id,
                rating=int(rating),
                reviewed_at=payload.get("reviewed_at"),
                has_media=has_media,
                position=int(payload.get("position") or position_offset + offset + 1),
            )
        )
    return candidates


def build_sample_target(job) -> int:
    """The job's review target is 1-300, defaulting to 50 (validated at creation)."""

    return int(job.review_target)


def import_sampled_reviews(
    spu,
    sampled_payloads,
    *,
    source_system: str,
    source_url: str = "",
    observed_at=None,
) -> dict:
    """Upsert the sampled reviews for one SPU through WP-12 services.

    Reviewers dedup only via the HMAC fingerprint of a stable public
    identifier; payload without ``reviewer_stable_id`` keeps a guest display
    snapshot and never merges by nickname. Returns per-review results and
    soft-deletes prior source reviews of this product that were not in the
    sample (they no longer appear in the source listing).
    """

    observed_at = observed_at or timezone.now()
    imported = []
    errors = []
    seen_ids = set()
    for payload in sampled_payloads or []:
        source_id = str((payload or {}).get("source_id") or "").strip()
        if not source_id:
            errors.append({"source_id": "", "error": "missing source_id"})
            continue
        seen_ids.add(source_id)
        try:
            raw_rating = payload.get("rating")
            if raw_rating is None:
                raise ReviewContentInvalid("rating is required.")
            reviewer = None
            stable_id = str(payload.get("reviewer_stable_id") or "").strip()
            if stable_id:
                reviewer, _ = get_or_create_reviewer_from_source(
                    source_system=source_system,
                    stable_public_identifier=stable_id,
                    display_name=payload.get("reviewer_name") or "",
                    observed_at=observed_at,
                )
            review, created = upsert_source_review(
                spu,
                source_system=source_system,
                source_id=source_id,
                rating=int(raw_rating),
                title=str(payload.get("title") or "")[:_MAX_TITLE],
                body=str(payload.get("body") or "")[:_MAX_BODY],
                locale=str(payload.get("locale") or ""),
                variant_text=str(payload.get("variant_text") or "")[:_MAX_VARIANT],
                likes_count=payload.get("likes_count"),
                source_reviewed_at=payload.get("reviewed_at"),
                source_url=source_url,
                source_position=payload.get("position") or {},
                reviewer=reviewer,
                guest_display_name=(payload.get("reviewer_name") or "") if reviewer is None else "",
                observed_at=observed_at,
            )
            imported.append({"source_id": source_id, "review": review, "created": created})
        except (ReviewContentInvalid, ReviewSourceIdentityInvalid, ValueError, TypeError) as exc:
            errors.append({"source_id": source_id, "error": str(exc)})

    # Soft-delete product reviews that disappeared from this sample window.
    deleted = []
    existing = Review.objects.filter(
        spu=spu, source_system=source_system, status=Review.Status.ACTIVE
    )
    for review in existing:
        if review.source_id not in seen_ids:
            mark_source_review_deleted(
                source_system=source_system,
                source_id=review.source_id,
                observed_at=observed_at,
            )
            deleted.append(review.source_id)

    return {
        "imported": imported,
        "errors": errors,
        "soft_deleted": deleted,
    }
