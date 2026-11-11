"""Check a real OpenWA session without displaying credentials or server responses."""

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 65536
TIMEOUT_SECONDS = 10
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,128}")


class NoRedirect(HTTPRedirectHandler):
    """Never forward the API key to another location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main() -> int:
    """Verify the selected session with one authenticated GET request."""
    origin = os.environ.get("OPENWA_BASE_URL", "")
    session = os.environ.get("OPENWA_SESSION_ID", "")
    api_key = os.environ.get("OPENWA_API_KEY", "")
    try:
        url = urlsplit(origin)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.password is not None or url.path not in ("", "/")
                or url.query or url.fragment or not url.port and ":" in url.netloc and not url.netloc.startswith("[")
                or not SESSION_ID_PATTERN.fullmatch(session) or not api_key
                or any(ord(char) < 33 or ord(char) > 126 for char in api_key)):
            raise ValueError
        request = Request(
            f"{origin.rstrip('/')}/api/sessions/{quote(session, safe='')}",
            headers={"X-API-Key": api_key, "Accept": "application/json", "Accept-Encoding": "identity"},
        )
        with build_opener(NoRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError
        data = json.loads(body)
        if (not isinstance(data, dict) or data.get("id") != session
                or data.get("status") != "ready" or data.get("engineLoaded", True) is not True):
            raise ValueError
    except (ValueError, HTTPError, URLError, TimeoutError, OSError, UnicodeError, RecursionError):
        print("OpenWA session check failed. Verify the secrets, connectivity and session status.", file=sys.stderr)
        return 1
    print("OpenWA session is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
