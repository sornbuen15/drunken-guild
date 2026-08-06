"""A guarded wrapper around :func:`urllib.request.urlopen`.

``urlopen`` honours every scheme its openers know about, including ``file://``
and ``ftp://``. So a URL that reaches it from configuration is not merely a
network destination — ``file:///etc/passwd`` is a valid argument, and the
response body comes back looking exactly like an HTTP response.

Today the Jira base URL comes from the registry, which is operator-controlled,
so this is defence in depth rather than a live hole. It stops being merely
defensive the moment the registry is shared, generated, or edited by anything
other than the person running the server — which is the direction this system
is deliberately heading.

Restricting the scheme at the one place that opens URLs is cheaper and more
durable than auditing every caller, so every outbound HTTP call in the codebase
goes through here.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import urllib.response
from typing import Final, cast

from .errors import ValidationError

#: The only schemes any part of this system has a reason to fetch.
ALLOWED_SCHEMES: Final = frozenset({"http", "https"})


def validate_url(url: str) -> str:
    """Return *url* if it is a plain http(s) URL with a host, else raise."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise ValidationError(
            f"Malformed URL: {url!r}",
            remediation=f"Check the URL in the registry ({exc}).",
        ) from None

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"URL scheme {parsed.scheme!r} is not allowed.",
            remediation=(
                "Only http:// and https:// are permitted. A file:// or ftp:// URL "
                "here would read local files through what looks like an API call."
            ),
        )

    if not parsed.netloc:
        raise ValidationError(
            f"URL has no host: {url!r}",
            remediation="Give a full URL, e.g. https://your-domain.atlassian.net",
        )

    return url


def open_url(
    request: urllib.request.Request,
    timeout: float,
) -> urllib.response.addinfourl:
    """Open *request* after checking its scheme.

    Takes a prepared :class:`~urllib.request.Request` so callers keep control of
    method, headers and body; this only decides whether it may be opened at all.
    """
    validate_url(request.full_url)
    # The scheme is checked immediately above. This is the only urlopen in the
    # codebase, which is the entire reason this module exists — every other call
    # site routes through here rather than suppressing the warning locally.
    # typeshed types urlopen as returning Any; cast so callers get the real
    # interface back rather than silently losing type checking downstream.
    response = urllib.request.urlopen(request, timeout=timeout)  # nosec B310
    return cast(urllib.response.addinfourl, response)
