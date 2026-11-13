from rest_framework.throttling import UserRateThrottle


class CoachCheckThrottle(UserRateThrottle):
    """Limits how often a user can make the server call their AI provider for a check, so that
    the instance cannot be used to hammer a provider (or to run up the user's own bill by
    accident). The counters live in the process cache, like the other rate limits."""

    scope = "coach_check"
