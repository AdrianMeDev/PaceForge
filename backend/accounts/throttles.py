from rest_framework.throttling import UserRateThrottle


class AccountExportThrottle(UserRateThrottle):
    """Limits how often a user can download the full data export, which reads every table
    that holds their data. The counters live in the process cache, like the other rate limits,
    and this one has a counter of its own."""

    scope = "account_export"


class InvitationEmailThrottle(UserRateThrottle):
    """Limits how many invitation emails an administrator can trigger, so the endpoint cannot be
    used to flood an address. The counters live in the process cache, like the other rate limits,
    and this one has a counter of its own."""

    scope = "invitation_email"


class AccountDeleteThrottle(UserRateThrottle):
    """Limits how often a user can try to delete the account, so the password and the second
    factor cannot be guessed through this endpoint. The counters live in the process cache,
    like the other rate limits, and this one has a counter of its own."""

    scope = "account_delete"
