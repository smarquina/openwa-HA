"""Monitor the configured OpenWA session."""

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .application import MessagingGateway
from .const import DOMAIN
from .errors import OpenWAError, OpenWAErrorCode

_LOGGER = logging.getLogger(__name__)
SESSION_READY = "ready"


class SessionCoordinator(DataUpdateCoordinator[str]):
    """Share one session check between diagnostic entities."""

    def __init__(self, hass: HomeAssistant, gateway: MessagingGateway, interval: int) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=interval))
        self._gateway = gateway

    async def _async_update_data(self) -> str:
        try:
            await self._gateway.async_check_session()
        except OpenWAError as err:
            if err.code in {
                OpenWAErrorCode.INVALID_AUTH, OpenWAErrorCode.FORBIDDEN,
                OpenWAErrorCode.SESSION_NOT_FOUND, OpenWAErrorCode.SESSION_NOT_READY,
                OpenWAErrorCode.CANNOT_CONNECT, OpenWAErrorCode.INVALID_TLS,
                OpenWAErrorCode.INVALID_RESPONSE,
            }:
                return err.code.value
            return OpenWAErrorCode.INVALID_RESPONSE.value
        return SESSION_READY
