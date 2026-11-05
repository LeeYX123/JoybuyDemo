"""Robots.txt parser fix for Scrapy 2.13.4.

``scrapy.robotstxt.ProtegoRobotParser.allowed`` calls
``rp.can_fetch(url, user_agent)`` with the arguments swapped (protego's
signature is ``can_fetch(user_agent, url)``), which forbids URLs at
random — measured live on 2026-11-05: the correct order allows
``/s?k=Kettles%20%26%20Toasters`` while Scrapy's order forbids it. This
parser restores the correct order; wired via ``ROBOTSTXT_PARSER`` so we
still obey robots.txt faithfully (docs/05 §8), just without the bug.
"""

from scrapy.robotstxt import ProtegoRobotParser
from scrapy.utils.python import to_unicode


class FixedProtegoRobotParser(ProtegoRobotParser):
    def allowed(self, url: str | bytes, user_agent: str | bytes) -> bool:
        return self.rp.can_fetch(to_unicode(user_agent), to_unicode(url))
