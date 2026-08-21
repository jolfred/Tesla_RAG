"""Политики повторов для VK API."""

import logging

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from vk_api.exceptions import VkApiError

logger = logging.getLogger("scraper.extractors.vk")

RETRYABLE_VK_CODES = {6, 9, 29}


class VkRateLimitError(Exception):
    pass


def raise_if_retryable(e: VkApiError) -> None:
    if e.code in RETRYABLE_VK_CODES:
        logger.warning("Retry [1/3]: ошибка %d (%s)", e.code, e)
        raise VkRateLimitError(str(e)) from e


vk_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, VkRateLimitError)),
    reraise=True,
)
