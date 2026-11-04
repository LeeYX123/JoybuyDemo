class OfferDomainError(Exception):
    pass


class MoneyValueInvalid(OfferDomainError):
    pass


class InventoryAdjustmentInvalid(OfferDomainError):
    pass


class InventoryIdempotencyConflict(OfferDomainError):
    pass


class OfferSourceIdentityInvalid(OfferDomainError):
    pass
