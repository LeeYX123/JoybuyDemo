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


class ImportSourceConflict(CrawlerControlError):
    """A source identity already belongs to different business data.

    导入层不自动改绑：来源身份（``OfferSourceIdentity`` / ``SkuSourceIdentity``）
    一旦指向另一条业务记录，静默改绑会改写历史 Offer/SKU 的归属。这里带中文
    可执行提示上抛，运行事件固定用 ``IMPORT_SOURCE_CONFLICT`` 便于筛选；
    原始英文异常只写 DEBUG 日志，不直接展示给用户。
    """

    event_code = "IMPORT_SOURCE_CONFLICT"
