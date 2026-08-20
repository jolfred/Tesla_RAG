from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from vk_api.exceptions import VkApiError


RETRYABLE_VK_ERRORS = {6, 9, 29}


def is_retryable_error(exception: Exception) -> bool:
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return True
    if isinstance(exception, VkApiError):
        return exception.code in RETRYABLE_VK_ERRORS
    return False


vk_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, VkApiError)),
    reraise=True,
)
