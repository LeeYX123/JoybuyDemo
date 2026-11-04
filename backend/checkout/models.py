import re
import uuid

from django.db import models

UK_POSTCODE_PATTERN = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?) ?(\d[A-Z]{2})$", re.IGNORECASE)


def is_supported_postcode(postcode: str) -> bool:
    """UK postcode format check; other regions are unsupported in phase 1."""

    return bool(UK_POSTCODE_PATTERN.match((postcode or "").strip()))


class Address(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(
        "accounts_buyers.BuyerAccount", on_delete=models.CASCADE, related_name="addresses"
    )
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True, default="")
    city = models.CharField(max_length=100)
    county = models.CharField(max_length=100, blank=True, default="")
    postcode = models.CharField(max_length=10)
    country_code = models.CharField(max_length=2, default="GB")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "buyer_address"
        indexes = [models.Index(fields=["account", "is_default"], name="address_account_idx")]

    @property
    def is_serviceable(self) -> bool:
        return self.country_code == "GB" and is_supported_postcode(self.postcode)

    def as_snapshot(self) -> dict:
        return {
            "full_name": self.full_name,
            "phone": self.phone,
            "line1": self.line1,
            "line2": self.line2,
            "city": self.city,
            "county": self.county,
            "postcode": self.postcode,
            "country_code": self.country_code,
        }
