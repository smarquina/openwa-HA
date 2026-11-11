"""HTTP client for the rmyndharis/OpenWA REST API."""

import asyncio
from http import HTTPStatus
from ipaddress import ip_address, ip_network
import json
import re

import aiohttp
from yarl import URL

_PRIVATE_NETWORKS = tuple(
    ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)
_SESSION_ID = re.compile(r"[A-Za-z0-9-]{1,128}")
_CHAT_ID = re.compile(r"(?:[0-9]{1,15}@c\.us|[0-9]{1,24}(?:-[0-9]{1,24})?@g\.us)")
_MAX_RESPONSE = 65536
_TRANSIENT = {429, 500, 502, 503, 504}


class OpenWAError(Exception):
    """Carry only a fixed, non-sensitive error code."""


def validate_endpoint(base_url: str, api_key: str, session_id: str, allow_http: bool) -> URL:
    """Validate a single origin and credentials before constructing requests."""
    if any(char.isspace() or ord(char) < 32 or char in "\\@?#" for char in base_url):
        raise OpenWAError("invalid_url")
    try:
        url = URL(base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.raw_host
            or url.raw_path != "/"
            or not 0 < url.port <= 65535
            or url.user is not None
            or "%" in url.raw_host
        ):
            raise ValueError
    except (ValueError, UnicodeError, OverflowError):
        raise OpenWAError("invalid_url") from None

    if url.scheme == "http":
        if allow_http is not True:
            raise OpenWAError("http_requires_opt_in")
        try:
            address = ip_address(url.raw_host)
        except ValueError:
            raise OpenWAError("http_requires_private_ip") from None
        if not any(address in network for network in _PRIVATE_NETWORKS):
            raise OpenWAError("http_requires_private_ip")

    if not api_key or not all(33 <= ord(char) <= 126 for char in api_key):
        raise OpenWAError("invalid_auth")
    if not _SESSION_ID.fullmatch(session_id):
        raise OpenWAError("invalid_session_id")
    return url.origin()


def valid_chat_id(value: str) -> bool:
    """Accept individual and group WhatsApp identifiers."""
    return _CHAT_ID.fullmatch(value) is not None


async def _read_object(response: aiohttp.ClientResponse, error: str) -> dict:
    """Read a bounded JSON object without exposing response contents."""
    if response.content_type != "application/json":
        raise OpenWAError(error)
    body = bytearray()
    async for chunk in response.content.iter_chunked(8192):
        body.extend(chunk)
        if len(body) > _MAX_RESPONSE:
            raise OpenWAError(error)
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        raise OpenWAError(error) from None
    if not isinstance(data, dict):
        raise OpenWAError(error)
    return data


class OpenWAClient:
    """Validate the selected session and submit outgoing text."""

    def __init__(
        self, http: aiohttp.ClientSession, origin: URL, api_key: str, session_id: str
    ) -> None:
        self._http = http
        self._headers = {"X-API-Key": api_key, "Accept-Encoding": "identity"}
        self._session_id = session_id
        self._session_url = origin / "api" / "sessions" / session_id

    async def async_check_session(self) -> None:
        """Retry a transient read failure once and require the selected session."""
        try:
            await self._async_read_session()
        except OpenWAError as err:
            if str(err) != "cannot_connect":
                raise
            await asyncio.sleep(1)
            await self._async_read_session()

    async def _async_read_session(self) -> None:
        try:
            async with self._http.get(
                self._session_url,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=5),
                allow_redirects=False,
                auto_decompress=False,
            ) as response:
                if response.status == 401:
                    raise OpenWAError("invalid_auth")
                if response.status == 403:
                    raise OpenWAError("forbidden")
                if response.status == 404:
                    raise OpenWAError("session_not_found")
                if response.status in _TRANSIENT:
                    raise OpenWAError("cannot_connect")
                if response.status != 200:
                    raise OpenWAError("invalid_response")
                data = await _read_object(response, "invalid_response")
        except (aiohttp.ClientSSLError, aiohttp.ServerFingerprintMismatch):
            raise OpenWAError("invalid_tls") from None
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise OpenWAError("cannot_connect") from None

        if data.get("id") != self._session_id or not isinstance(data.get("status"), str):
            raise OpenWAError("invalid_response")
        if data["status"] != "ready" or data.get("engineLoaded", True) is not True:
            raise OpenWAError("session_not_ready")

    async def async_send_text(self, chat_id: str, message: str) -> None:
        """Perform one POST. Never replay it."""
        try:
            async with self._http.post(
                self._session_url / "messages" / "send-text",
                headers=self._headers,
                json={"chatId": chat_id, "text": message},
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=False,
                auto_decompress=False,
            ) as response:
                if response.status == 401:
                    raise OpenWAError("invalid_auth")
                if response.status == 403:
                    raise OpenWAError("forbidden")
                if response.status in (400, 404, 413):
                    raise OpenWAError("send_rejected")
                if response.status != HTTPStatus.CREATED:
                    raise OpenWAError("send_unknown")
                data = await _read_object(response, "send_unknown")
                if not isinstance(data.get("messageId"), str) or not data["messageId"].strip():
                    raise OpenWAError("send_unknown")
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise OpenWAError("send_unknown") from None
