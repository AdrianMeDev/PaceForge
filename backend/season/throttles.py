from rest_framework.throttling import UserRateThrottle


class SeasonGenerateThrottle(UserRateThrottle):
    """Limits how often a user can make the server call their AI provider for a season. A call
    costs the user's own money, is several times as long as one for a week and can take minutes, so
    a script or a stuck button must not be able to repeat it. The counters live in the process
    cache, like the other rate limits."""

    scope = "season_generate"
