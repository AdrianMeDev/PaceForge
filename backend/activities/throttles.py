from rest_framework.throttling import UserRateThrottle


class ActivityImportThrottle(UserRateThrottle):
    """Limits how many files a user can send to the parsers per minute.

    Every attempt counts, successful or not, and a throttled request never reaches the parser.
    The counters live in the process cache, like the other rate limits.
    """

    scope = "activity_import"
