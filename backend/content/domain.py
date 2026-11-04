class ContentDomainError(Exception):
    pass


class CmsPayloadInvalid(ContentDomainError):
    pass


class CmsPageStateInvalid(ContentDomainError):
    pass
