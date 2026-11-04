class CatalogDomainError(Exception):
    pass


class CategoryTreeInvalid(CatalogDomainError):
    pass


class CategoryVersionConflict(CatalogDomainError):
    pass


class CategoryMoveInvalid(CatalogDomainError):
    pass


class ProductSourceIdentityInvalid(CatalogDomainError):
    pass


class SkuSpecificationInvalid(CatalogDomainError):
    pass


class FieldValueInvalid(CatalogDomainError):
    pass


class OverrideStateInvalid(CatalogDomainError):
    pass
