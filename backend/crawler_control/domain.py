class CrawlerControlError(Exception):
    pass


class CrawlJobParamsInvalid(CrawlerControlError):
    pass


class CrawlJobStateInvalid(CrawlerControlError):
    pass


class CrawlRunStateInvalid(CrawlerControlError):
    pass


class CrawlAccountStateInvalid(CrawlerControlError):
    pass


class CrawlSessionSecretInvalid(CrawlerControlError):
    """Refused to store the payload, e.g. it contains password-like fields."""


class RiskControlPaused(CrawlerControlError):
    """The account/run is paused by risk control; only manual review resumes it."""


class RawResponseInvalid(CrawlerControlError):
    pass
