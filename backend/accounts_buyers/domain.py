class BuyerDomainError(Exception):
    pass


class VerificationCodeInvalid(BuyerDomainError):
    pass


class VerificationCodeExpired(BuyerDomainError):
    pass


class VerificationCodeLocked(BuyerDomainError):
    pass


class VerificationDeliveryUnavailable(BuyerDomainError):
    pass
