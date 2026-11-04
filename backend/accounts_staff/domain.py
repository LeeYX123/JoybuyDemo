class StaffDomainError(Exception):
    pass


class TotpNotEnrolled(StaffDomainError):
    pass


class TotpInvalid(StaffDomainError):
    pass


class TotpReplay(StaffDomainError):
    pass
