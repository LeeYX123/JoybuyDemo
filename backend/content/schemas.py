"""CMS module payload schemas and validation (WP-21).

Each schema describes the fields a renderer may rely on. Validation is
lenient by design: unknown extra keys pass through, and the renderer is
responsible for safe degradation; here we only guarantee the structural
minimum so an obviously broken payload never reaches production.
"""

from content.domain import CmsPayloadInvalid

MODULE_TYPES = ("hero", "banner", "product_pool", "rich_text", "link_grid", "campaign_grid")

SCHEMAS = {
    "hero": {
        "required": ("heading", "cta_href"),
        "optional": ("subheading", "cta_label", "image_path", "theme"),
    },
    "banner": {
        "required": ("href",),
        "optional": ("image_path", "alt", "label", "theme"),
    },
    "product_pool": {
        "required": ("title", "products"),
        "optional": ("href",),
    },
    "rich_text": {
        "required": ("heading", "body"),
        "optional": (),
    },
    "link_grid": {
        "required": ("items",),
        "optional": ("title", "variant"),
    },
    "campaign_grid": {
        "required": ("items",),
        "optional": ("title",),
    },
}

PRODUCT_FIELDS_REQUIRED = ("public_id", "title")
PRODUCT_FIELDS_OPTIONAL = (
    "price",
    "currency",
    "image_path",
    "rating",
    "review_count",
    "badge",
    "href",
)


def validate_module_payload(module_type: str, payload: dict) -> dict:
    """Validate one payload against its schema; returns the payload as-is."""

    if module_type not in SCHEMAS:
        raise CmsPayloadInvalid(f"Unknown module type: {module_type}.")
    if not isinstance(payload, dict):
        raise CmsPayloadInvalid("Module payload must be an object.")

    schema = SCHEMAS[module_type]
    for field in schema["required"]:
        value = payload.get(field)
        if value is None or value == "":
            raise CmsPayloadInvalid(f"Module '{module_type}' requires field '{field}'.")

    if module_type == "product_pool":
        products = payload["products"]
        if not isinstance(products, list):
            raise CmsPayloadInvalid("product_pool.products must be a list.")
        for index, product in enumerate(products):
            if not isinstance(product, dict):
                raise CmsPayloadInvalid(f"product_pool.products[{index}] must be an object.")
            for field in PRODUCT_FIELDS_REQUIRED:
                if not str(product.get(field) or "").strip():
                    raise CmsPayloadInvalid(
                        f"product_pool.products[{index}] requires field '{field}'."
                    )
    if module_type == "link_grid":
        items = payload["items"]
        if not isinstance(items, list):
            raise CmsPayloadInvalid("link_grid.items must be a list.")
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not str(item.get("label") or "").strip():
                raise CmsPayloadInvalid(f"link_grid.items[{index}] requires field 'label'.")
    if module_type == "campaign_grid":
        items = payload["items"]
        if not isinstance(items, list):
            raise CmsPayloadInvalid("campaign_grid.items must be a list.")
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not str(item.get("title") or "").strip():
                raise CmsPayloadInvalid(f"campaign_grid.items[{index}] requires field 'title'.")
    return payload
