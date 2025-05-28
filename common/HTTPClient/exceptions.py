class RouterError(Exception):  # pragma: no cover
    """Represents an exception returned by the remote or local API."""

    def __init__(self, status, message=None):
        self.status = status
        self.message = message

    def __str__(self):
        if self.message is None:
            return self.status
        else:
            return "%s (%s)" % (self.status, self.message)


class RouterApiError(RouterError):
    """Represents an exception returned by a routing engine, i.e. 400 <= HTTP status code <= 500"""


class RouterServerError(RouterError):
    """Represents an exception returned by a server, i.e. 500 <= HTTP"""


class RouterNotFound(Exception):
    """Represents an exception raised when router can not be found by name."""


class Timeout(Exception):  # pragma: no cover
    """The request timed out."""


class JSONParseError(Exception):  # pragma: no cover
    """The Json response can't be parsed.."""


class RetriableRequest(Exception):  # pragma: no cover
    """Signifies that the request can be retried."""


class OverQueryLimit(RouterError, RetriableRequest):
    """Signifies that the request failed because the client exceeded its query rate limit.

    Normally we treat this as a retrievable condition, but we allow the calling code to specify that these requests should
    not be retried.
    """
