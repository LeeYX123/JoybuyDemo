class MediaDomainError(Exception):
    pass


class MediaPathInvalid(MediaDomainError):
    pass


class MediaContentInvalid(MediaDomainError):
    pass


class MediaKindInvalid(MediaDomainError):
    pass
