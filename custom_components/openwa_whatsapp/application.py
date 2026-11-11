"""Application use case and gateway contract for outbound notifications."""

import re
from typing import Protocol

from .errors import OpenWAError, OpenWAErrorCode

# OpenWA send-text contract: https://docs.open-wa.org/guides/sending-messages
MAX_MESSAGE_LENGTH = 4096
_CHAT_ID = re.compile(r"(?:[0-9]{1,15}@c\.us|[0-9]{1,24}(?:-[0-9]{1,24})?@g\.us)")


class MessagingGateway(Protocol):
    """Operations required from an outgoing messaging gateway."""

    async def async_check_session(self) -> None:
        """Check that the selected session is ready."""

    async def async_send_text(self, chat_id: str, message: str) -> None:
        """Submit a single message."""


class SendNotification:
    """Send one notification using the configured gateway."""

    def __init__(self, gateway: MessagingGateway) -> None:
        self._gateway = gateway

    async def execute(self, chat_id: str, message: str) -> None:
        """Submit one notification."""
        if not _CHAT_ID.fullmatch(chat_id):
            raise OpenWAError(OpenWAErrorCode.INVALID_CHAT_ID)
        if not message.strip() or len(message) > MAX_MESSAGE_LENGTH:
            raise OpenWAError(OpenWAErrorCode.INVALID_MESSAGE)
        await self._gateway.async_check_session()
        await self._gateway.async_send_text(chat_id, message)
