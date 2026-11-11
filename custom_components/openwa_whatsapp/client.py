"""HTTP client for the rmyndharis/OpenWA REST API."""

import asyncio
from enum import StrEnum
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


class OpenWAErrorCode(StrEnum):
    """Stable error codes used by the integration."""

    INVALID_URL = "invalid_url"
    HTTP_REQUIRES_OPT_IN = "http_requires_opt_in"
    HTTP_REQUIRES_PRIVATE_IP = "http_requires_private_ip"
    INVALID_AUTH = "invalid_auth"
    INVALID_SESSION_ID = "invalid_session_id"
    CANNOT_CONNECT = "cannot_connect"
    INVALID_TLS = "invalid_tls"
    INVALID_RESPONSE = "invalid_response"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_NOT_READY = "session_not_ready"
    FORBIDDEN = "forbidden"
    SEND_REJECTED = "send_rejected"
    SEND_UNKNOWN = "send_unknown"


class OpenWAError(Exception):
    """Carry only a fixed, non-sensitive error code."""


def validate_endpoint(base_url: str, api_key: str, session_id: str, allow_http: bool) -> URL:
    """Validate a single origin and credentials before constructing requests."""
    if any(char.isspace() or ord(char) < 32 or char in "\\@?#" for char in base_url):
        raise OpenWAError(OpenWAErrorCode.INVALID_URL)
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
        raise OpenWAError(OpenWAErrorCode.INVALID_URL) from None

    if url.scheme == "http":
        if allow_http is not True:
            raise OpenWAError(OpenWAErrorCode.HTTP_REQUIRES_OPT_IN)
        try:
            address = ip_address(url.raw_host)
        except ValueError:
            raise OpenWAError(OpenWAErrorCode.HTTP_REQUIRES_PRIVATE_IP) from None
        if not any(address in network for network in _PRIVATE_NETWORKS):
            raise OpenWAError(OpenWAErrorCode.HTTP_REQUIRES_PRIVATE_IP)

    if not api_key or not all(33 <= ord(char) <= 126 for char in api_key):
        raise OpenWAError(OpenWAErrorCode.INVALID_AUTH)
    if not _SESSION_ID.fullmatch(session_id):
        raise OpenWAError(OpenWAErrorCode.INVALID_SESSION_ID)
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
            if str(err) != OpenWAErrorCode.CANNOT_CONNECT:
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
                    raise OpenWAError(OpenWAErrorCode.INVALID_AUTH)
                if response.status == 403:
                    raise OpenWAError(OpenWAErrorCode.FORBIDDEN)
                if response.status == 404:
                    raise OpenWAError(OpenWAErrorCode.SESSION_NOT_FOUND)
                if response.status in _TRANSIENT:
                    raise OpenWAError(OpenWAErrorCode.CANNOT_CONNECT)
                if response.status != 200:
                    raise OpenWAError(OpenWAErrorCode.INVALID_RESPONSE)
                data = await _read_object(response, OpenWAErrorCode.INVALID_RESPONSE)
        except (aiohttp.ClientSSLError, aiohttp.ServerFingerprintMismatch):
            raise OpenWAError(OpenWAErrorCode.INVALID_TLS) from None
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise OpenWAError(OpenWAErrorCode.CANNOT_CONNECT) from None

        if data.get("id") != self._session_id or not isinstance(data.get("status"), str):
            raise OpenWAError(OpenWAErrorCode.INVALID_RESPONSE)
        if data["status"] != "ready" or data.get("engineLoaded", True) is not True:
            raise OpenWAError(OpenWAErrorCode.SESSION_NOT_READY)

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
                    raise OpenWAError(OpenWAErrorCode.INVALID_AUTH)
                if response.status == 403:
                    raise OpenWAError(OpenWAErrorCode.FORBIDDEN)
                if response.status in (400, 404, 413):
                    raise OpenWAError(OpenWAErrorCode.SEND_REJECTED)
                if response.status != HTTPStatus.CREATED:
                    raise OpenWAError(OpenWAErrorCode.SEND_UNKNOWN)
                data = await _read_object(response, OpenWAErrorCode.SEND_UNKNOWN)
                if not isinstance(data.get("messageId"), str) or not data["messageId"].strip():
                    raise OpenWAError(OpenWAErrorCode.SEND_UNKNOWN)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise OpenWAError(OpenWAErrorCode.SEND_UNKNOWN) from None
