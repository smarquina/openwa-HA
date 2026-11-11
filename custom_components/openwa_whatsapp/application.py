"""Application use case and gateway contract for outbound notifications."""

from typing import Protocol


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
        await self._gateway.async_check_session()
        await self._gateway.async_send_text(chat_id, message)
