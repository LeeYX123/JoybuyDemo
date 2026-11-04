"""Category discovery and crawl-plan expansion (WP-15).

Turns a :class:`crawler_control.models.CrawlJob` into an ordered, deduped,
reproducible set of listing targets:

1. resolve the category scope (current only vs including subcategories)
   against the bound or latest published tree version;
2. build paginated listing targets per scope honouring the job limit and
   sort strategy (RANDOM uses the persisted seed, so reruns are identical);
3. parse listing pages and dedupe product URLs across categories while
   keeping the first-seen source rank.
"""

import math
import random
from dataclasses import dataclass, field

from catalog.models import (
    SourceCategorySnapshot,
    SourceCategoryTreeVersion,
)
from catalog.services import source_category_descendants
from crawler_control.models import CrawlJob

SORT_QUERY_PARAMS = {
    CrawlJob.ListingSort.SOURCE_DEFAULT: "default",
    CrawlJob.ListingSort.BEST_SELLING: "sales",
    CrawlJob.ListingSort.TOP_RATED: "rating",
    CrawlJob.ListingSort.NEWEST: "new",
    CrawlJob.ListingSort.RANDOM: "default",
}

DEFAULT_PER_PAGE = 30


@dataclass(frozen=True)
class CategoryScope:
    source_category_pk: int
    source_id: str
    name: str
    depth: int
    path: str
    tree_version_key: str


@dataclass(frozen=True)
class ListingTarget:
    scope: CategoryScope
    page: int
    url: str


@dataclass
class CrawlPlan:
    job_pk: int
    scopes: list[CategoryScope] = field(default_factory=list)
    targets: list[ListingTarget] = field(default_factory=list)
    planned_product_count: int = 0


def resolve_tree_version(job: CrawlJob) -> SourceCategoryTreeVersion:
    """A job pins its snapshot at expansion time if not bound at creation."""

    if job.source_tree_version_id:
        return job.source_tree_version
    latest = (
        SourceCategoryTreeVersion.objects.filter(
            catalog=job.source_catalog, status=SourceCategoryTreeVersion.Status.PUBLISHED
        )
        .order_by("-captured_at", "-pk")
        .first()
    )
    if latest is None:
        raise ValueError(
            f"Source catalog '{job.source_catalog.source_system}' has no published tree version."
        )
    return latest


def expand_job_categories(job: CrawlJob) -> list[CategoryScope]:
    version = resolve_tree_version(job)
    snapshot = SourceCategorySnapshot.objects.get(
        tree_version=version, category=job.source_category
    )
    if job.category_mode == CrawlJob.CategoryMode.CURRENT_ONLY:
        snapshots = [snapshot]
    else:
        snapshots = [snapshot, *source_category_descendants(snapshot)]
    return [
        CategoryScope(
            source_category_pk=item.category_id,
            source_id=item.category.source_id,
            name=item.name,
            depth=item.depth,
            path=item.path,
            tree_version_key=version.version_key,
        )
        for item in snapshots
    ]


def build_listing_targets(
    scopes: list[CategoryScope],
    *,
    listing_sort: str,
    product_limit: int,
    base_url: str,
    per_page: int = DEFAULT_PER_PAGE,
) -> list[ListingTarget]:
    """Deterministic, paginated listing targets per scope."""

    if product_limit < 1:
        raise ValueError("product_limit must be positive.")
    if per_page < 1:
        raise ValueError("per_page must be positive.")
    sort_param = SORT_QUERY_PARAMS[listing_sort]
    targets = []
    for scope in scopes:
        page_count = max(1, math.ceil(product_limit / per_page))
        for page in range(1, page_count + 1):
            url = f"{base_url.rstrip('/')}/{scope.source_id}?sort={sort_param}&page={page}"
            targets.append(ListingTarget(scope=scope, page=page, url=url))
    return targets


def order_targets(targets: list[ListingTarget], *, listing_sort: str, random_seed=None):
    """RANDOM shuffles with the persisted seed; every other sort keeps source order."""

    ordered = list(targets)
    if listing_sort == CrawlJob.ListingSort.RANDOM:
        if random_seed is None:
            raise ValueError("RANDOM sort requires the job's persisted random_seed.")
        random.Random(random_seed).shuffle(ordered)
    return ordered


def build_crawl_plan(
    job: CrawlJob,
    *,
    base_url: str,
    per_page: int = DEFAULT_PER_PAGE,
) -> CrawlPlan:
    scopes = expand_job_categories(job)
    targets = build_listing_targets(
        scopes,
        listing_sort=job.listing_sort,
        product_limit=job.product_limit,
        base_url=base_url,
        per_page=per_page,
    )
    ordered = order_targets(targets, listing_sort=job.listing_sort, random_seed=job.random_seed)
    return CrawlPlan(
        job_pk=job.pk,
        scopes=scopes,
        targets=ordered,
        planned_product_count=job.product_limit * len(scopes),
    )


def dedupe_product_urls(entries) -> list:
    """Keep the first-seen entry per product URL across category listings."""

    seen = {}
    for entry in entries:
        if entry.source_url not in seen:
            seen[entry.source_url] = entry
    return list(seen.values())
