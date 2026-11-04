import hashlib
import hmac

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from reviews.domain import (
    ReviewContentInvalid,
    ReviewerIdentityInvalid,
    ReviewSourceIdentityInvalid,
)
from reviews.models import Review, ReviewMedia, ReviewVersion, VirtualReviewer


def source_fingerprint(source_system: str, stable_public_identifier: str) -> str:
    """HMAC-SHA256 fingerprint; the reversible source id is never persisted."""

    normalized_system = (source_system or "").strip().casefold()
    stable = (stable_public_identifier or "").strip()
    if not normalized_system or not stable:
        raise ReviewerIdentityInvalid(
            "source_system and a stable public identifier are required for reviewer dedup."
        )
    message = f"{normalized_system}:{stable}".encode()
    return hmac.new(
        settings.SOURCE_FINGERPRINT_HMAC_KEY.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()


def get_or_create_reviewer_from_source(
    *,
    source_system: str,
    stable_public_identifier: str,
    display_name: str = "",
    avatar=None,
    display_attributes=None,
    observed_at=None,
) -> tuple[VirtualReviewer, bool]:
    """Dedup reviewers only through the HMAC fingerprint of a stable id.

    Reviews without a stable identifier must not create a reviewer at all;
    nickname equality is never treated as identity.
    """

    normalized_system = (source_system or "").strip().casefold()
    fingerprint = source_fingerprint(normalized_system, stable_public_identifier)
    observed_at = observed_at or timezone.now()
    attributes = display_attributes or {}

    existing = VirtualReviewer.objects.filter(
        source_system=normalized_system,
        fingerprint=fingerprint,
    ).first()
    if existing:
        fields = ["last_seen_at", "updated_at"]
        existing.last_seen_at = observed_at
        if display_name.strip() and display_name.strip() != existing.display_name:
            existing.display_name = display_name.strip()
            fields.append("display_name")
        if avatar is not None and avatar.pk != existing.avatar_id:
            existing.avatar = avatar
            fields.append("avatar")
        if attributes and attributes != existing.display_attributes:
            existing.display_attributes = attributes
            fields.append("display_attributes")
        existing.save(update_fields=fields)
        return existing, False

    reviewer = VirtualReviewer.objects.create(
        source_system=normalized_system,
        fingerprint=fingerprint,
        display_name=display_name.strip(),
        avatar=avatar,
        display_attributes=attributes,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )
    return reviewer, True


def _validate_rating(rating) -> int:
    if isinstance(rating, bool) or not isinstance(rating, int):
        raise ReviewContentInvalid("Rating must be an integer between 1 and 5.")
    if not 1 <= rating <= 5:
        raise ReviewContentInvalid("Rating must be between 1 and 5.")
    return rating


def _validate_text_field(value, *, field: str, max_length: int) -> str:
    text = (value or "").strip()
    if len(text) > max_length:
        raise ReviewContentInvalid(f"{field} exceeds {max_length} characters.")
    return text


def compute_review_content_hash(
    *,
    rating: int,
    title: str,
    body: str,
    variant_text: str,
    likes_count,
) -> str:
    canonical = "|".join(
        [
            str(rating),
            _validate_text_field(title, field="title", max_length=300),
            _validate_text_field(body, field="body", max_length=20000),
            _validate_text_field(variant_text, field="variant_text", max_length=300),
            "" if likes_count is None else str(likes_count),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upsert_source_review(
    spu,
    *,
    source_system: str,
    source_id: str,
    rating,
    title: str = "",
    body: str = "",
    locale: str = "",
    variant_text: str = "",
    likes_count=None,
    source_reviewed_at=None,
    source_url: str = "",
    source_position=None,
    reviewer=None,
    guest_display_name: str = "",
    observed_at=None,
) -> tuple[Review, bool]:
    """Idempotently import a source review; content changes keep version history."""

    normalized_system = (source_system or "").strip().casefold()
    normalized_id = (source_id or "").strip()
    if not normalized_system or not normalized_id:
        raise ReviewSourceIdentityInvalid("source_system and source_id are required.")
    if reviewer is None and not guest_display_name.strip():
        raise ReviewContentInvalid(
            "A reviewer or a guest display snapshot is required for every review."
        )
    validated_rating = _validate_rating(rating)
    observed_at = observed_at or timezone.now()
    validated_title = _validate_text_field(title, field="title", max_length=300)
    validated_body = _validate_text_field(body, field="body", max_length=20000)
    validated_variant = _validate_text_field(variant_text, field="variant_text", max_length=300)
    if likes_count is not None and (
        isinstance(likes_count, bool) or not isinstance(likes_count, int)
    ):
        raise ReviewContentInvalid("likes_count must be an integer or null when not shown.")
    content_hash = compute_review_content_hash(
        rating=validated_rating,
        title=validated_title,
        body=validated_body,
        variant_text=validated_variant,
        likes_count=likes_count,
    )
    position = source_position or {}

    with transaction.atomic():
        existing = (
            Review.objects.select_for_update()
            .filter(
                source_system=normalized_system,
                source_id=normalized_id,
                origin=Review.Origin.SOURCE,
            )
            .first()
        )
        if existing is None:
            review = Review.objects.create(
                spu=spu,
                origin=Review.Origin.SOURCE,
                source_system=normalized_system,
                source_id=normalized_id,
                source_url=source_url.strip(),
                reviewer=reviewer,
                guest_display_name=guest_display_name.strip(),
                rating=validated_rating,
                title=validated_title,
                body=validated_body,
                locale=locale.strip(),
                variant_text=validated_variant,
                likes_count=likes_count,
                source_reviewed_at=source_reviewed_at,
                source_position=position,
                content_hash=content_hash,
                status=Review.Status.ACTIVE,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            ReviewVersion.objects.create(
                review=review,
                content_hash=content_hash,
                rating=validated_rating,
                title=validated_title,
                body=validated_body,
                variant_text=validated_variant,
                likes_count=likes_count,
                change_kind=ReviewVersion.ChangeKind.CREATED,
                observed_at=observed_at,
            )
            return review, True

        if existing.spu_id != spu.pk:
            raise ReviewSourceIdentityInvalid(
                "The source review identity is already attached to a different product."
            )
        existing.source_url = source_url.strip()
        existing.locale = locale.strip() or existing.locale
        existing.source_reviewed_at = source_reviewed_at or existing.source_reviewed_at
        existing.source_position = position or existing.source_position
        existing.last_seen_at = observed_at
        fields = [
            "source_url",
            "locale",
            "source_reviewed_at",
            "source_position",
            "last_seen_at",
            "updated_at",
        ]
        if reviewer is not None:
            existing.reviewer = reviewer
            existing.guest_display_name = ""
            fields += ["reviewer", "guest_display_name"]
        if content_hash != existing.content_hash:
            ReviewVersion.objects.create(
                review=existing,
                content_hash=existing.content_hash,
                rating=existing.rating,
                title=existing.title,
                body=existing.body,
                variant_text=existing.variant_text,
                likes_count=existing.likes_count,
                change_kind=ReviewVersion.ChangeKind.UPDATED,
                observed_at=observed_at,
            )
            existing.rating = validated_rating
            existing.title = validated_title
            existing.body = validated_body
            existing.variant_text = validated_variant
            existing.likes_count = likes_count
            existing.content_hash = content_hash
            fields += [
                "rating",
                "title",
                "body",
                "variant_text",
                "likes_count",
                "content_hash",
            ]
        if existing.status == Review.Status.DELETED:
            # The review re-appeared at the source; restore visibility.
            existing.status = Review.Status.ACTIVE
            existing.deleted_at = None
            fields += ["status", "deleted_at"]
        existing.save(update_fields=fields)
        return existing, False


def mark_source_review_deleted(
    *,
    source_system: str,
    source_id: str,
    observed_at=None,
) -> Review:
    """Soft-delete a review that disappeared from the source; history is kept."""

    normalized_system = (source_system or "").strip().casefold()
    normalized_id = (source_id or "").strip()
    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        review = (
            Review.objects.select_for_update()
            .filter(
                source_system=normalized_system,
                source_id=normalized_id,
                origin=Review.Origin.SOURCE,
            )
            .first()
        )
        if review is None:
            raise ReviewSourceIdentityInvalid("No source review exists for this identity.")
        if review.status == Review.Status.DELETED:
            review.last_seen_at = observed_at
            review.save(update_fields=["last_seen_at", "updated_at"])
            return review
        ReviewVersion.objects.create(
            review=review,
            content_hash=review.content_hash,
            rating=review.rating,
            title=review.title,
            body=review.body,
            variant_text=review.variant_text,
            likes_count=review.likes_count,
            change_kind=ReviewVersion.ChangeKind.DELETED,
            observed_at=observed_at,
        )
        review.status = Review.Status.DELETED
        review.deleted_at = observed_at
        review.last_seen_at = observed_at
        review.save(update_fields=["status", "deleted_at", "last_seen_at", "updated_at"])
        return review


def attach_review_media(
    review: Review,
    asset,
    *,
    media_kind: str,
    source_url: str = "",
    position: int = 0,
    observed_at=None,
) -> tuple[ReviewMedia, bool]:
    """Idempotently attach downloaded media to a review."""

    if media_kind not in ReviewMedia.MediaKind.values:
        raise ReviewContentInvalid("Review media kind must be IMAGE or VIDEO.")
    if asset is None or getattr(asset, "pk", None) is None:
        raise ReviewContentInvalid("Review media requires a stored MediaAsset.")
    observed_at = observed_at or timezone.now()
    existing = ReviewMedia.objects.filter(review=review, asset=asset).first()
    if existing:
        existing.last_seen_at = observed_at
        existing.position = position
        existing.source_url = source_url.strip() or existing.source_url
        existing.save(update_fields=["last_seen_at", "position", "source_url"])
        return existing, False
    return (
        ReviewMedia.objects.create(
            review=review,
            asset=asset,
            media_kind=media_kind,
            position=position,
            source_url=source_url.strip(),
            first_seen_at=observed_at,
            last_seen_at=observed_at,
        ),
        True,
    )
