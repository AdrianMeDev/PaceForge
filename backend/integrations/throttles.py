from rest_framework.throttling import UserRateThrottle


class ProviderConnectionThrottle(UserRateThrottle):
    """Limits how often a user can make the server call a provider (connect and check).

    Both endpoints share one counter per user, so the instance cannot be used to hammer a
    provider's API. The counters live in the process cache, like the other rate limits.
    """

    scope = "provider_connection"
