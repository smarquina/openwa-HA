"""Stable integration errors, independent of transport and presentation."""

from enum import StrEnum


class OpenWAErrorCode(StrEnum):
    """Stable error codes used by the integration."""

    INVALID_CHAT_ID = "invalid_chat_id"
    INVALID_MESSAGE = "invalid_message"
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
    SELECT_ENTRY = "select_entry"
    ENTRY_UNAVAILABLE = "entry_unavailable"


class OpenWAError(Exception):
    """Carry only a fixed, non-sensitive error code."""

    def __init__(self, code: OpenWAErrorCode) -> None:
        self.code = code
        super().__init__(code)


