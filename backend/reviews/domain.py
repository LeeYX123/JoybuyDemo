class ReviewsDomainError(Exception):
    pass


class ReviewerIdentityInvalid(ReviewsDomainError):
    pass


class ReviewContentInvalid(ReviewsDomainError):
    pass


class ReviewSourceIdentityInvalid(ReviewsDomainError):
    pass
