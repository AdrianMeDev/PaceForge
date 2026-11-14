from rest_framework.throttling import UserRateThrottle


class ReviewCommentThrottle(UserRateThrottle):
    """Limits how often a user can make the server call their AI provider for a comment on a week.
    Every request is a call that costs the user's own money and can take a minute, so a script or
    a stuck button must not be able to repeat it. The counters live in the process cache, like the
    other rate limits, and this one has a counter of its own."""

    scope = "review_comment"
