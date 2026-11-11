"""Check application boundaries and user-facing translations."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from custom_components.openwa_whatsapp.application import SendNotification
from custom_components.openwa_whatsapp.errors import OpenWAError, OpenWAErrorCode


@pytest.mark.parametrize(
    ("chat_id", "message", "error"),
    [("invalid", "hello", OpenWAErrorCode.INVALID_CHAT_ID),
     ("15551234567@c.us", " ", OpenWAErrorCode.INVALID_MESSAGE)],
)
async def test_invalid_notification_does_not_access_gateway(chat_id, message, error):
    gateway = AsyncMock()
    with pytest.raises(OpenWAError) as caught:
        await SendNotification(gateway).execute(chat_id, message)
    assert caught.value.code == error
    gateway.async_check_session.assert_not_awaited()
    gateway.async_send_text.assert_not_awaited()


async def test_failed_session_never_sends():
    gateway = AsyncMock()
    gateway.async_check_session.side_effect = OpenWAError(OpenWAErrorCode.SESSION_NOT_READY)
    with pytest.raises(OpenWAError):
        await SendNotification(gateway).execute("15551234567@c.us", "hello")
    gateway.async_send_text.assert_not_awaited()


async def test_valid_notification_checks_session_then_sends_once():
    gateway = AsyncMock()
    await SendNotification(gateway).execute("15551234567@c.us", "hello")
    assert gateway.method_calls == [
        ("async_check_session", (), {}),
        ("async_send_text", ("15551234567@c.us", "hello"), {}),
    ]


def test_exception_and_service_translations_are_complete():
    root = Path(__file__).resolve().parents[1] / "custom_components/openwa_whatsapp/translations"
    translations = [json.loads((root / f"{lang}.json").read_text()) for lang in ("en", "es")]
    for data in translations:
        assert {code.value for code in OpenWAErrorCode} <= data["exceptions"].keys()
        action = data["services"]["send_message"]
        assert action["name"] and action["description"]
        assert set(action["fields"]) == {"chat_id", "message", "entry_id"}
        assert all(field.get("name") and field.get("description") for field in action["fields"].values())
    assert translations[0]["config"]["error"].keys() == translations[1]["config"]["error"].keys()
